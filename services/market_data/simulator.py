import asyncio
from datetime import datetime
from packages.contracts.provider import MarketDataProvider
from packages.contracts.market import MarketDataStatus
from packages.domain.market import Candle, SimulationSpec
from services.market_simulator.generator import CandleGenerator
from typing import AsyncIterator

class SimulatorMarketDataProvider(MarketDataProvider):
    def __init__(self, spec: SimulationSpec, interval_seconds: float = 2.0):
        self.spec = spec
        self.interval_seconds = interval_seconds
        self.generator = CandleGenerator(spec)
        self.cursor = 0
        self.last_close: dict[int, str] = {} # Just dummy
    
    async def get_historical_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        candles = []
        # Generate some historical candles up to now
        for i in range(1, limit + 1):
            c = self.generator.next_closed(i)
            candles.append(c)
            self.cursor = i
        return candles

    async def subscribe(self) -> AsyncIterator[Candle]:
        while True:
            self.cursor += 1
            candle = self.generator.next_closed(self.cursor)
            yield candle
            await asyncio.sleep(self.interval_seconds)

    def get_status(self) -> MarketDataStatus:
        return MarketDataStatus(
            provider="simulator",
            feed="local",
            state="connected",
            symbols=["TEST"]
        )
