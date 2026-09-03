"""Valores de mercado; nenhuma dependência de framework, banco ou execução."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

Regime = Literal["uptrend", "downtrend", "sideways", "volatile"]


@dataclass(frozen=True)
class SimulationSpec:
    seed: int = 42
    start: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def __post_init__(self) -> None:
        if self.start.utcoffset() != timedelta(0):
            raise ValueError("O relógio simulado deve começar em UTC.")
        if self.start.minute or self.start.second or self.start.microsecond:
            raise ValueError("O relógio deve começar em uma hora cheia.")

    @property
    def stream_id(self) -> UUID:
        # Intervalo de apresentação não altera a sequência de mercado.
        return uuid5(
            NAMESPACE_URL, f"trading-bot/ohlcv-v1/TEST/1h/{self.seed}/{self.start.isoformat()}"
        )


@dataclass(frozen=True)
class Candle:
    candle_id: UUID
    stream_id: UUID
    sequence: int
    symbol: str
    timeframe: str
    provider: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    regime: Regime

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if not all(p.is_finite() and p > 0 for p in prices):
            raise ValueError("Preços devem ser decimais positivos e finitos.")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("OHLC inválido.")
        if self.volume < 0 or self.sequence < 1:
            raise ValueError("Volume ou sequência inválida.")
        if self.open_time.utcoffset() != timedelta(0) or self.close_time.utcoffset() != timedelta(
            0
        ):
            raise ValueError("Timestamps devem estar em UTC.")
        if self.close_time - self.open_time != timedelta(hours=1):
            raise ValueError("Candle deve representar exatamente uma hora fechada.")
