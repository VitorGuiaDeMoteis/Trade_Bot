"""Identidade de mercado independente do cursor de entrega."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from packages.domain.timeframes import timeframe_duration


def series_id(provider: str, symbol: str, timeframe: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"trading-bot/series-v2/{provider}/{symbol}/{timeframe}")


@dataclass(frozen=True)
class MarketBar:
    provider: str
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_closed: bool

    def __post_init__(self) -> None:
        duration = timeframe_duration(self.timeframe)
        if self.provider not in {"alpaca", "simulator"} or not self.symbol:
            raise ValueError("invalid_market_identity")
        if self.open_time.utcoffset() != timedelta(0) or self.close_time.utcoffset() != timedelta(
            0
        ):
            raise ValueError("utc_required")
        if self.close_time - self.open_time != duration:
            raise ValueError("invalid_bar_duration")
        prices = self.open, self.high, self.low, self.close
        if not all(isinstance(p, Decimal) and p.is_finite() and p > 0 for p in prices):
            raise ValueError("invalid_prices")
        if any(p >= Decimal("1e18") or p != p.quantize(Decimal("0.0000000001")) for p in prices):
            raise ValueError("price_outside_storage_precision")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("invalid_ohlc")
        if not isinstance(self.volume, int) or isinstance(self.volume, bool) or self.volume < 0:
            raise ValueError("invalid_volume")

    @property
    def candle_id(self) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"trading-bot/bar-v2/{self.provider}/{self.symbol}/{self.timeframe}/{self.open_time.isoformat()}",
        )
