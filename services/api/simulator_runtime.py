"""Infrastructure orchestration with durable per-series replay and explicit failure."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.market import MarketDataStatus, ProviderState
from packages.contracts.provider import MarketDataProvider
from packages.domain.market import Candle
from packages.domain.market_bar import MarketBar
from services.api.config import Settings
from services.api.market_store import MarketStore
from services.market_data.alpaca_provider import BACKOFF, AlpacaMarketDataProvider
from services.market_data.errors import ContentConflict, ProviderError
from services.market_data.simulator import SimulatorMarketDataProvider

logger = logging.getLogger("trading_bot.market")


class SimulatorRuntime:
    def __init__(
        self,
        settings: Settings,
        store: MarketStore,
        provider: MarketDataProvider,
        stores: dict[str, MarketStore] | None = None,
    ) -> None:
        self.settings, self.store, self.provider = settings, store, provider
        self.stores = stores or {settings.symbols[0]: store}
        self.task: asyncio.Task[None] | None = None
        self.state: ProviderState = "stopped"
        self.error: str | None = None
        self.last_persisted_at: datetime | None = None
        self.last_progress = monotonic()

    def start(self) -> None:
        enabled = self.settings.market_data_provider == "alpaca" or self.settings.simulator_enabled
        if enabled and (self.task is None or self.task.done()):
            self.state, self.error = "starting", None
            self.task = asyncio.create_task(self._run(), name="market-data")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.provider.close()
        self.state = "stopped"

    def status(self) -> MarketDataStatus:
        status = self.provider.get_status()
        state = self.state
        if state == "connected":
            state = status.state
            if status.provider == "simulator" and monotonic() - self.last_progress > max(
                10,
                self.settings.simulator_interval_seconds * 2 + 5,
            ):
                state = "stalled"
        return status.model_copy(
            update={
                "state": state,
                "error": self.error or status.error,
                "last_persisted_at": self.last_persisted_at,
            }
        )

    def _failure(self, code: str, state: ProviderState = "degraded") -> None:
        self.error, self.state = code, state
        logger.warning(
            json.dumps(
                {
                    "event": "market.ingestion.failed",
                    "reason": code,
                    "state": state,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "correlation_id": str(uuid4()),
                }
            )
        )

    async def _persist(self, bar: Candle | MarketBar) -> None:
        attempt = 0
        while True:
            try:
                event = await asyncio.to_thread(self.stores[bar.symbol].append, bar)
                self.last_persisted_at = event.occurred_at
                self.last_progress = monotonic()
                self.state, self.error = "connected", None
                return
            except SQLAlchemyError:
                self._failure("database_unavailable")
                await asyncio.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                attempt += 1

    async def _run(self) -> None:
        try:
            if isinstance(self.provider, SimulatorMarketDataProvider):
                await self._simulate()
                return
            attempt = 0
            while True:
                try:
                    for symbol, store in self.stores.items():
                        last = await asyncio.to_thread(store.latest_open)
                        history = await self.provider.get_historical_candles(
                            symbol,
                            self.settings.market_timeframe,
                            start=last,
                        )
                        for bar in history:
                            await self._persist(bar)
                        if isinstance(self.provider, AlpacaMarketDataProvider) and history:
                            self.provider.resume_from(symbol, history[-1].open_time)
                    break
                except SQLAlchemyError:
                    self._failure("database_unavailable")
                except ProviderError as error:
                    if not error.retryable:
                        raise
                    self._failure(error.code, "reconnecting")
                await asyncio.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                attempt += 1
            self.state, self.error = "connected", None
            async for bar in self.provider.subscribe():
                await self._persist(bar)
        except ContentConflict:
            self._failure("market_identity_content_conflict")
        except ProviderError as error:
            self._failure(error.code, self.provider.get_status().state)
        except (ValueError, OverflowError):
            self._failure("invalid_candle")
        except Exception:
            # Unexpected programming failures must be visible, without secret-bearing repr.
            self._failure("unexpected_ingestion_failure")
            raise

    async def _simulate(self) -> None:
        assert isinstance(self.provider, SimulatorMarketDataProvider)
        while True:
            try:
                event = await asyncio.to_thread(self.store.advance, self.provider.generator)
                self.last_persisted_at = event.occurred_at
                self.last_progress = monotonic()
                self.state, self.error = "connected", None
            except SQLAlchemyError:
                self._failure("database_unavailable")
            await asyncio.sleep(self.settings.simulator_interval_seconds)
