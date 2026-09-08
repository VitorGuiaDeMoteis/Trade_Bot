from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from packages.domain.market_bar import MarketBar
from services.market_data.aggregator import TimeframeAggregator


def make_bar(minute: int, close: str = "10.0") -> MarketBar:
    # 14:00 UTC is 10:00 EDT (Regular Session)
    dt = datetime(2026, 9, 3, 14, minute, tzinfo=UTC)
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
        is_closed=True,
    )


def test_aggregator_1m_to_5m_15m_1h():
    closed = []
    agg = TimeframeAggregator(["5m", "15m", "1h"], lambda b: closed.append(b))

    # 14:00 to 14:04 UTC (10:00 - 10:04 EDT)
    for i in range(5):
        agg.process(make_bar(i, close=str(10 + i)))

    assert len(closed) == 1
    assert closed[0].timeframe == "5m"
    assert closed[0].open_time.minute == 0
    assert closed[0].close == Decimal("14.0")
    assert closed[0].volume == 500

    # 14:05 to 14:14 UTC -> produces two 5m, and one 15m
    for i in range(5, 15):
        agg.process(make_bar(i, close=str(10 + i)))

    assert len(closed) == 4
    timeframes = [b.timeframe for b in closed]
    assert timeframes.count("5m") == 3
    assert timeframes.count("15m") == 1


def ny_bar(day: datetime, hour: int, minute: int, symbol: str = "SPY") -> MarketBar:
    opened = day.replace(hour=hour, minute=minute, tzinfo=ZoneInfo("America/New_York"))
    return MarketBar(
        "alpaca",
        symbol,
        "1m",
        opened.astimezone(UTC),
        (opened + timedelta(minutes=1)).astimezone(UTC),
        Decimal("10"),
        Decimal("11"),
        Decimal("9"),
        Decimal("10"),
        100,
        True,
    )


def test_regular_session_boundaries_and_final_buckets():
    closed = []
    agg = TimeframeAggregator(["1m", "5m", "15m", "1h"], closed.append)
    day = datetime(2026, 7, 6)
    agg.process(ny_bar(day, 9, 29))
    for minute in range(30, 60):
        agg.process(ny_bar(day, 15, minute))
    agg.process(ny_bar(day, 16, 0))
    assert sum(bar.timeframe == "1m" for bar in closed) == 30
    assert sum(bar.timeframe == "5m" for bar in closed) == 6
    assert sum(bar.timeframe == "15m" for bar in closed) == 2
    assert sum(bar.timeframe == "1h" for bar in closed) == 0
    assert [
        bar.close_time.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
        for bar in closed
        if bar.timeframe == "15m"
    ] == ["15:45", "16:00"]


def test_multisymbol_duplicate_late_gap_and_dst():
    closed = []
    agg = TimeframeAggregator(["5m"], closed.append)
    summer = datetime(2026, 7, 6)
    winter = datetime(2026, 1, 5)
    for minute in range(30, 35):
        agg.process(ny_bar(summer, 9, minute, "SPY"))
        agg.process(ny_bar(summer, 9, minute, "AAPL"))
    assert {(bar.symbol, bar.open_time.hour) for bar in closed} == {("SPY", 13), ("AAPL", 13)}

    # Duplicate and late minutes cannot complete or mutate a later bucket.
    agg.process(ny_bar(summer, 9, 34, "SPY"))
    agg.process(ny_bar(summer, 9, 33, "SPY"))
    assert len(closed) == 2

    gap_output = []
    gap = TimeframeAggregator(["5m"], gap_output.append)
    for minute in (30, 31, 33, 34):
        gap.process(ny_bar(summer, 9, minute))
    for minute in range(0, 5):
        gap.process(ny_bar(summer, 10, minute))
    assert [(bar.open_time.minute, bar.volume) for bar in gap_output] == [(0, 500)]

    dst = []
    for day in (winter, summer):
        item = TimeframeAggregator(["5m"], dst.append)
        for minute in range(30, 35):
            item.process(ny_bar(day, 9, minute))
    assert [bar.open_time.hour for bar in dst] == [14, 13]
