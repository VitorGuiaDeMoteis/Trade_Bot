"""Orquestração de infraestrutura. O gerador de mercado permanece puro."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.market import SimulationStatus, SimulatorState
from services.api.config import Settings
from services.api.market_store import MarketStore
from services.market_simulator.generator import CandleGenerator

logger = logging.getLogger("trading_bot.simulator")


class SimulatorRuntime:
    def __init__(self, settings: Settings, store: MarketStore, generator: CandleGenerator) -> None:
        self.settings = settings
        self.store = store
        self.generator = generator
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

    def status(self) -> SimulationStatus:
        state = self.state
        if state == "running" and monotonic() - self.last_progress > max(
            10,
            self.settings.simulator_interval_seconds * 2 + 5,
        ):
            state = "stalled"
        return SimulationStatus(
            state=state,
            seed=self.generator.spec.seed,
            start=self.generator.spec.start,
            interval_seconds=self.settings.simulator_interval_seconds,
            accelerated=self.settings.simulator_interval_seconds < 3600,
            last_persisted_at=self.last_persisted_at,
            error=self.error,
        )

    async def _run(self) -> None:
        while True:
            try:
                event = await asyncio.to_thread(self.store.advance, self.generator)
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
                            "correlation_id": str(self.generator.spec.stream_id),
                            "reason": self.error,
                        }
                    )
                )
            await asyncio.sleep(self.settings.simulator_interval_seconds)
