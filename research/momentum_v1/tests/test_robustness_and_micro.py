from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.momentum_v1.micro_replay import run_micro_replay
from research.momentum_v1.run_experiments import _common_substitution_data, run_substitutions


def _substitution_fixture() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    universe = ["SPY", "EFA", "EEM", "TLT", "GLD", "DBC", "VNQ"]
    replacements = ["VTI", "VXUS", "IEMG", "VGLT", "IAU", "PDBC", "SCHH"]
    dates = pd.bdate_range("2018-01-02", "2021-12-31")
    primary = pd.DataFrame(index=dates)
    substitutes = pd.DataFrame(index=dates[20:])
    for offset, symbol in enumerate(universe):
        close = 100.0 * np.cumprod(np.full(len(dates), 1.0002 + offset * 0.00001))
        primary[("Open", symbol)] = close
        primary[("Close", symbol)] = close
    primary[("Close", "DTB3")] = 1.0
    for offset, symbol in enumerate(replacements):
        close = 100.0 * np.cumprod(np.full(len(substitutes), 1.0002 + offset * 0.00001))
        substitutes[("Open", symbol)] = close
        substitutes[("Close", symbol)] = close
    return primary, substitutes, universe


def test_common_overlap_excludes_noncommon_sessions() -> None:
    primary, substitutes, _ = _substitution_fixture()
    common = _common_substitution_data(primary, substitutes, "SPY", "VTI")
    assert common.index.min() == substitutes.index.min()
    assert len(common) == len(substitutes)


def test_am_substitution_runs_on_common_overlap() -> None:
    primary, substitutes, universe = _substitution_fixture()
    results = run_substitutions(primary, substitutes, universe, "2020-01-01", "2021-12-31")
    assert "AM_substitution" in results["SPY->VTI"]
    assert str(results["SPY->VTI"]["common_start"]) >= "2020-01-01"


def test_ram_substitution_runs_on_common_overlap() -> None:
    primary, substitutes, universe = _substitution_fixture()
    results = run_substitutions(primary, substitutes, universe, "2020-01-01", "2021-12-31")
    assert "RAM_substitution" in results["VNQ->SCHH"]


def test_micro_replay_fractional_rounding_and_minimum() -> None:
    date = pd.Timestamp("2020-01-02")
    data = pd.DataFrame(index=pd.DatetimeIndex([date]))
    data[("Open", "A")] = 300.0
    data[("Close", "A")] = 300.0
    targets = pd.DataFrame({"A": [1.0]}, index=[date])
    replay = run_micro_replay(data, ["A"], targets, initial_capital=50.0, min_notional=1.0, frac_precision=6)
    assert replay.quantities.iloc[0, 0] == pytest.approx(round(50.0 / (1.0 + 0.00025) / 300.0, 6))
    assert replay.records.iloc[0]["orders_below_minimum"] == 0.0
    assert abs(replay.records.iloc[0]["rounding_residual"]) < 0.001


def test_micro_replay_detects_below_minimum_order() -> None:
    date = pd.Timestamp("2020-01-02")
    data = pd.DataFrame(index=pd.DatetimeIndex([date]))
    data[("Open", "A")] = 10.0
    data[("Close", "A")] = 10.0
    targets = pd.DataFrame({"A": [0.01]}, index=[date])
    replay = run_micro_replay(data, ["A"], targets, initial_capital=50.0, min_notional=1.0)
    assert replay.records.iloc[0]["orders_below_minimum"] == 1.0
    assert replay.quantities.iloc[0, 0] == 0.0
