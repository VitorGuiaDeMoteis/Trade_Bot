"""Orquestração de infraestrutura. O gerador de mercado permanece puro."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.market import MarketDataStatus, SimulatorState
from services.api.config import Settings
from services.api.market_store import MarketStore
from packages.contracts.provider import MarketDataProvider

logger = logging.getLogger("trading_bot.simulator")


class SimulatorRuntime:
    def __init__(self, settings: Settings, store: MarketStore, provider: MarketDataProvider) -> None:
        self.settings = settings
        self.store = store
        self.provider = provider
        self.task: asyncio.Task[None] | None = None
        self.state: SimulatorState = "stopped"
        self.error: str | None = None
        self.last_persisted_at: datetime | None = None
        self.last_progress = monotonic()

    def start(self) -> None:
        if self.settings.simulator_enabled and (self.task is None or self.task.done()):
            self.state = "starting"
            self.task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.state = "stopped"

    def status(self) -> MarketDataStatus:
        state = self.state
        if state == "running" and monotonic() - self.last_progress > max(
            10,
            self.settings.simulator_interval_seconds * 2 + 5,
        ):
            state = "stalled"
            
        provider_status = self.provider.get_status()
            
        return MarketDataStatus(
            state=state,
            provider=provider_status.get("provider"),
            feed=provider_status.get("feed"),
            symbols=provider_status.get("symbols"),
            last_persisted_at=self.last_persisted_at,
            error=self.error,
        )

    async def _run(self) -> None:
        try:
            # Backfill historical candles
            symbols = self.settings.market_symbols.split(",")
            for symbol in symbols:
                symbol = symbol.strip()
                if not symbol: continue
                
                historical_candles = await self.provider.get_historical_candles(symbol, self.settings.market_timeframe)
                for candle in historical_candles:
                    try:
                        event = await asyncio.to_thread(self.store.append, candle)
                        self.last_persisted_at = event.occurred_at
                    except ValueError:
                        pass # Ignore duplicates or sequence errors from backfill
            
            # Subscribe to real-time stream
            async for candle in self.provider.subscribe():
                try:
                    event = await asyncio.to_thread(self.store.append, candle)
                    self.last_persisted_at = event.occurred_at
                    self.last_progress = monotonic()
                    self.state = "running"
                    self.error = None
                    logger.info(
                        json.dumps(
                            {
                                "event": "market.candle.persisted",
                                "occurred_at": datetime.now(UTC).isoformat(),
                                "correlation_id": str(event.correlation_id),
                                "stream_id": str(event.stream_id),
                                "sequence": event.sequence,
                            }
                        )
                    )
                except (SQLAlchemyError, ValueError, OverflowError) as error:
                    self.state = "degraded"
                    self.error = (
                        "database_unavailable"
                        if isinstance(error, SQLAlchemyError)
                        else "invalid_candle"
                    )
                    logger.warning(
                        json.dumps(
                            {
                                "event": "simulator.degraded",
                                "occurred_at": datetime.now(UTC).isoformat(),
                                "correlation_id": str(candle.stream_id),
                                "reason": self.error,
                            }
                        )
                    )
        except Exception as e:
            self.state = "stopped"
            self.error = str(e)
            logger.error(f"Provider failed: {e}")
