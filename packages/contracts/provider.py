import abc
from collections.abc import AsyncIterator
from datetime import datetime

from packages.contracts.market import MarketDataStatus
from packages.domain.market import Candle
from packages.domain.market_bar import MarketBar


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    async def get_historical_candles(
        self, symbol: str, timeframe: str, limit: int = 200, *, start: datetime | None = None
    ) -> list[MarketBar | Candle]:
        """Fetch historical closed candles."""
        pass

    @abc.abstractmethod
    def subscribe(self) -> AsyncIterator[MarketBar | Candle]:
        """Subscribe to real-time closed candles."""
        pass

    @abc.abstractmethod
    def get_status(self) -> MarketDataStatus:
        """Get provider health status."""
        pass

    async def close(self) -> None:
        """Libera somente recursos pertencentes ao provider."""
        return None
