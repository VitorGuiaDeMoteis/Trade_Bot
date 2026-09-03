"""Deterministic simulator adapter; runtime resumes from PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

from packages.contracts.market import MarketDataStatus
from packages.contracts.provider import MarketDataProvider
from packages.domain.market import Candle, SimulationSpec
from packages.domain.market_bar import MarketBar
from services.market_simulator.generator import CandleGenerator


class SimulatorMarketDataProvider(MarketDataProvider):
    def __init__(self, spec: SimulationSpec, interval_seconds: float = 2.0) -> None:
        self.spec = spec
        self.interval_seconds = interval_seconds
        self.generator = CandleGenerator(spec)
        self.cursor = 0
        self.last_close = Decimal("100.0000")

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        *,
        start: datetime | None = None,
    ) -> list[MarketBar | Candle]:
        if symbol != "TEST" or timeframe != "1h" or not 1 <= limit <= 10000:
            raise ValueError("invalid_simulator_series")
        result: list[MarketBar | Candle] = []
        previous = Decimal("100.0000")
        for index in range(1, limit + 1):
            candle = self.generator.next_closed(index, previous)
            previous = candle.close
            if start is None or candle.open_time >= start:
                result.append(candle)
        return result

    async def subscribe(self) -> AsyncIterator[Candle | MarketBar]:
        while True:
            self.cursor += 1
            candle = self.generator.next_closed(self.cursor, self.last_close)
            self.last_close = candle.close
            yield candle
            await asyncio.sleep(self.interval_seconds)

    def get_status(self) -> MarketDataStatus:
        return MarketDataStatus(
            provider="simulator",
            feed="local",
            state="connected",
            symbols=["TEST"],
            accelerated=True,
            interval_seconds=self.interval_seconds,
        )
