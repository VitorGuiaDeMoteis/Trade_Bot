from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from packages.domain.market import SimulationSpec
from services.market_simulator.generator import REGIMES, CandleGenerator


def sequence(spec, count=120):
    generator = CandleGenerator(spec)
    values = []
    last = Decimal("100.0000")
    for index in range(1, count + 1):
        candle = generator.next_closed(index, last)
        values.append(candle)
        last = candle.close
    return values


def test_same_seed_and_controlled_clock_are_reproducible():
    spec = SimulationSpec(42, datetime(2020, 1, 1, tzinfo=UTC))
    assert sequence(spec) == sequence(spec)
    assert sequence(spec)[0].close_time == datetime(2020, 1, 1, 1, tzinfo=UTC)


def test_different_seeds_and_clocks_have_different_streams():
    left, right = sequence(SimulationSpec(1)), sequence(SimulationSpec(2))
    assert [c.close for c in left] != [c.close for c in right]
    assert left[0].stream_id != right[0].stream_id
    assert (
        SimulationSpec(1).stream_id != SimulationSpec(1, datetime(2025, 1, 1, tzinfo=UTC)).stream_id
    )


@pytest.mark.parametrize("seed", [0, 1, 42, -100, 999999])
def test_ohlcv_regimes_unique_sorted_timestamps(seed):
    values = sequence(SimulationSpec(seed), 500)
    assert {c.regime for c in values} == set(REGIMES)
    assert len({c.candle_id for c in values}) == len(values)
    assert len({c.open_time for c in values}) == len(values)
    assert [c.open_time for c in values] == sorted(c.open_time for c in values)
    for index, candle in enumerate(values):
        assert candle.high >= max(candle.open, candle.close)
        assert candle.low <= min(candle.open, candle.close)
        assert candle.high >= candle.low > 0
        assert candle.volume >= 0
        assert candle.close_time - candle.open_time == timedelta(hours=1)
        assert candle.close_time.utcoffset() == timedelta(0)
        assert isinstance(candle.close, Decimal)
        if index:
            assert candle.open == values[index - 1].close
            assert candle.open_time == values[index - 1].close_time


def test_domain_rejects_invalid_candle_and_clock():
    candle = sequence(SimulationSpec(), 1)[0]
    for changes in [
        {"low": candle.high + 1},
        {"volume": -1},
        {"close": Decimal("NaN")},
        {"sequence": 0},
        {"close_time": candle.open_time},
        {"open_time": datetime(2026, 1, 1)},
    ]:
        with pytest.raises(ValueError):
            replace(candle, **changes)
    with pytest.raises(ValueError):
        SimulationSpec(start=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        SimulationSpec(start=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))
