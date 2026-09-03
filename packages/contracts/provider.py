import abc
from packages.domain.market import Candle
from packages.contracts.market import MarketDataStatus
from typing import AsyncIterator

class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    async def get_historical_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        """Fetch historical closed candles."""
        pass

    @abc.abstractmethod
    async def subscribe(self) -> AsyncIterator[Candle]:
        """Subscribe to real-time closed candles."""
        pass

    @abc.abstractmethod
    def get_status(self) -> MarketDataStatus:
        """Get provider health status."""
        pass
