import pytest
from datetime import datetime, timezone, timedelta
from packages.contracts.observer import AIObserverSnapshot, ObserverCandle

def test_snapshot_no_leakage():
    c = ObserverCandle(
        symbol="AAPL",
        open_time=datetime(2023, 1, 1, 10, tzinfo=timezone.utc),
        close_time=datetime(2023, 1, 1, 11, tzinfo=timezone.utc),
        open="100", high="105", low="99", close="102", volume=1000, is_closed=True
    )
    snap = AIObserverSnapshot(
        schema_version="1.0",
        as_of_utc=datetime(2023, 1, 1, 11, tzinfo=timezone.utc),
        provider="simulator",
        session_state="connected",
        symbols=("AAPL",),
        timeframe="1h",
        candles=(c,),
        signals=tuple([]),
        risk_decisions=tuple([]),
        paper=None,
        accepted_backtest=None
    )
    
    payload = snap.payload().decode("utf-8")
    assert "BUY" not in payload, "Payload must not leak BUY"
    assert "SELL" not in payload, "Payload must not leak SELL"
    assert "strategy_signal" not in payload, "Payload must not leak strategy state"
    assert "paper" not in payload or '"paper":null' in payload or '"paper": null' in payload, "Payload must not leak paper portfolio state"
