from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from packages.domain.market import Candle
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy


def test_strategy_generates_correct_signals():
    engine = BaseStrategy()
    current_time = datetime.now(UTC)

    # Bullish candle -> BUY
    candle_bull = Candle(
        candle_id=uuid4(),
        stream_id=uuid4(),
        sequence=1,
        symbol="TEST",
        timeframe="1h",
        provider="simulator",
        open_time=current_time - timedelta(hours=1),
        close_time=current_time,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=1000,
        regime="uptrend",
    )
    signal = engine.process_candle(candle_bull, current_time)
    assert signal.signal_type == "BUY"

    # Bearish candle -> SELL
    candle_bear = Candle(
        candle_id=uuid4(),
        stream_id=uuid4(),
        sequence=2,
        symbol="TEST",
        timeframe="1h",
        provider="simulator",
        open_time=current_time - timedelta(hours=1),
        close_time=current_time,
        open=Decimal("105"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("100"),
        volume=1000,
        regime="downtrend",
    )
    signal2 = engine.process_candle(candle_bear, current_time)
    assert signal2.signal_type == "SELL"


def test_risk_engine_decisions():
    strategy = BaseStrategy()
    risk = RiskEngine()
    current_time = datetime.now(UTC)

    candle = Candle(
        candle_id=uuid4(),
        stream_id=uuid4(),
        sequence=1,
        symbol="TEST",
        timeframe="1h",
        provider="simulator",
        open_time=current_time - timedelta(hours=1),
        close_time=current_time,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=1000,
        regime="uptrend",
    )

    signal = strategy.process_candle(candle, current_time)

    # Normal approval
    decision = risk.evaluate(signal, current_time)
    assert decision.decision == "APPROVED"

    # System paused
    decision_paused = risk.evaluate(signal, current_time, system_paused=True)
    assert decision_paused.decision == "REJECTED"
    assert "pausado" in decision_paused.reason

    # Expired signal
    future_time = current_time + timedelta(hours=2)
    decision_expired = risk.evaluate(signal, future_time)
    assert decision_expired.decision == "REJECTED"
    assert "vencido" in decision_expired.reason
