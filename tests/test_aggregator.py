from datetime import UTC, datetime, timedelta
from decimal import Decimal

from packages.domain.market_bar import MarketBar
from services.market_data.aggregator import TimeframeAggregator


def make_bar(minute: int, close: str = "10.0") -> MarketBar:
    dt = datetime(2026, 9, 3, 9, minute, tzinfo=UTC)
    return MarketBar(
        provider="alpaca",
        symbol="SPY",
        timeframe="1m",
        open_time=dt,
        close_time=dt + timedelta(minutes=1),
        open=Decimal("10.0"),
        high=Decimal(close) + Decimal("1.0"),
        low=Decimal("9.0"),
        close=Decimal(close),
        volume=100,
        is_closed=True
    )

def test_aggregator_1m_to_5m_15m_1h():
    closed = []
    agg = TimeframeAggregator(["5m", "15m", "1h"], lambda b: closed.append(b))
    
    # 09:00 to 09:04 -> produces one 5m
    for i in range(5):
        agg.process(make_bar(i, close=str(10+i)))
        
    assert len(closed) == 1
    assert closed[0].timeframe == "5m"
    assert closed[0].open_time.minute == 30
    assert closed[0].close == Decimal("14.0")
    assert closed[0].volume == 500

    # 09:05 to 09:14 -> produces two 5m, and one 15m at 09:14 close
    for i in range(5, 15):
        agg.process(make_bar(i, close=str(10+i)))
    
    assert len(closed) == 4
    timeframes = [b.timeframe for b in closed]
    assert timeframes.count("5m") == 3
    assert timeframes.count("15m") == 1
