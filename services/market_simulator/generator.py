"""Gerador puro e reproduzível: relógio lógico e aleatoriedade por índice."""

import hashlib
import random
from decimal import Decimal, localcontext
from uuid import uuid5

from packages.domain.market import Candle, Regime, SimulationSpec
from packages.domain.timeframes import timeframe_duration

REGIMES: tuple[Regime, ...] = ("uptrend", "downtrend", "sideways", "volatile")



class CandleGenerator:
    def __init__(self, spec: SimulationSpec, timeframe: str = "1h") -> None:
        self.spec = spec
        self.timeframe = timeframe
        self.duration = timeframe_duration(timeframe)

    def next_closed(self, sequence: int, previous_close: Decimal = Decimal("100.0000")) -> Candle:
        if sequence < 1:
            raise ValueError("Sequência começa em 1.")
        digest = hashlib.sha256(
            f"{self.spec.seed}:{sequence}:{self.timeframe}:ohlcv-v1".encode()
        ).digest()
        rng = random.Random(int.from_bytes(digest))
        regime = REGIMES[((sequence - 1) // 24) % len(REGIMES)]
        drift, noise = {
            "uptrend": (60, 25),
            "downtrend": (-60, 25),
            "sideways": (0, 20),
            "volatile": (0, 250),
        }[regime]
        with localcontext() as context:
            context.prec = 32
            quantum = Decimal("0.0001")
            movement = Decimal(drift + rng.randint(-noise, noise)) / Decimal(10000)
            close = max(Decimal("1"), previous_close * (1 + movement)).quantize(quantum)
            wick = Decimal(rng.randint(1, noise + 20)) / Decimal(10000)
            high = (max(previous_close, close) * (1 + wick)).quantize(quantum)
            low = max(quantum, min(previous_close, close) * (1 - wick)).quantize(quantum)
        open_time = self.spec.start + (sequence - 1) * self.duration
        # O relógio virtual avança ao fechamento; não é uma previsão de hora real.
        return Candle(
            candle_id=uuid5(self.spec.stream_id, str(sequence)),
            stream_id=self.spec.stream_id,
            sequence=sequence,
            symbol="TEST",
            timeframe=self.timeframe,
            provider="simulator",
            open_time=open_time,
            close_time=open_time + self.duration,
            open=previous_close,
            high=high,
            low=low,
            close=close,
            volume=rng.randint(0, 5000 if regime == "volatile" else 2000),
            regime=regime,
        )
