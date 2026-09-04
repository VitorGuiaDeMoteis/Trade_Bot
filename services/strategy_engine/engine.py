"""Motor de estratégia determinístico da v0.1 (M2)."""

from datetime import datetime
from uuid import uuid4

from packages.domain.market import Candle
from packages.domain.strategy import Signal, SignalType


class BaseStrategy:
    VERSION = "v1-deterministic"

    def process_candle(self, candle: Candle, current_time: datetime) -> Signal:
        """Processa um candle e retorna um sinal determinístico."""
        if not candle.is_closed or (
            candle.provider == "alpaca" and candle.close_time > current_time
        ):
            raise ValueError("partial_candle")
        signal_type: SignalType = "HOLD"
        if candle.close > candle.open:
            signal_type = "BUY"
        elif candle.close < candle.open:
            signal_type = "SELL"

        return Signal(
            signal_id=uuid4(),
            candle_id=candle.candle_id,
            stream_id=candle.stream_id,
            strategy_version=self.VERSION,
            signal_type=signal_type,
            generated_at=current_time,
            reason={
                "BUY": "Fechamento acima da abertura.",
                "SELL": "Fechamento abaixo da abertura.",
                "HOLD": "Abertura e fechamento equivalentes. Sem ação.",
            }[signal_type],
        )
