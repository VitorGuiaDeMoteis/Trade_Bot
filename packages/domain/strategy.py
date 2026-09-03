"""Definição de domínio para Sinais gerados pelas Estratégias."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

SignalType = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class Signal:
    signal_id: UUID
    candle_id: UUID
    stream_id: UUID
    strategy_version: str
    signal_type: SignalType
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.generated_at.utcoffset() != timedelta(0):
            raise ValueError("O relógio deve estar em UTC.")
        if not self.strategy_version:
            raise ValueError("A versão da estratégia é obrigatória.")
