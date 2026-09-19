import json
from pathlib import Path

import pandas as pd
import pytest

from research.mean_reversion_v1.data import validate_artifacts
from research.mean_reversion_v1.engine import run_backtest
from research.mean_reversion_v1.strategies import MeanReversionParams


def test_primary_universe_remains_exactly_four_etfs():
    config = json.loads(Path("research/mean_reversion_v1/config.json").read_text())
    assert config["universe"] == ["SPY", "IWM", "EFA", "EEM"]


def test_qqq_does_not_affect_primary_portfolio_construction():
    dates = pd.bdate_range("2004-01-01", periods=5)
    data = pd.DataFrame(index=dates)
    for sym in ["SPY", "IWM", "EFA", "EEM"]:
        data[("Close", sym)] = 100.0
        data[("Open", sym)] = 100.0
    data[("Close", "DTB3")] = 0.0

    params = MeanReversionParams(N=2, L=2, Z_entry=-2.0, Z_exit=0.0, M=10)
    # primary universe passed explicitly
    res = run_backtest(data, ["SPY", "IWM", "EFA", "EEM"], params, dates[0], dates[-1], slots=4)
    # Positions should only have 4 * 2 (cash+pos) + 1 (CASH) = 9 columns
    assert "QQQ" not in res.positions.columns
    assert len(res.positions.columns) == 9


def test_qqq_robustness_produces_5_x_20_percent_slots():
    dates = pd.bdate_range("2004-01-01", periods=5)
    data = pd.DataFrame(index=dates)
    for sym in ["SPY", "IWM", "EFA", "EEM", "QQQ"]:
        data[("Close", sym)] = 100.0
        data[("Open", sym)] = 100.0
    data[("Close", "DTB3")] = 0.0

    params = MeanReversionParams(N=2, L=2, Z_entry=-2.0, Z_exit=0.0, M=10)
    # robustness universe passed explicitly
    res = run_backtest(
        data, ["SPY", "IWM", "EFA", "EEM", "QQQ"], params, dates[0], dates[-1], slots=5
    )

    # 10_000_000 initial capital / 5 slots = 2_000_000 per slot
    first_day = res.positions.iloc[0]
    for sym in ["SPY", "IWM", "EFA", "EEM", "QQQ"]:
        assert first_day[f"{sym}_cash"] == 2_000_000.0


def test_missing_qqq_artifact_causes_preflight_error(tmp_path):
    # Mock artifacts dir
    (tmp_path / "primary.parquet").touch()
    (tmp_path / "fred_dtb3.parquet").touch()
    (tmp_path / "substitutes.parquet").touch()
    # INTENTIONALLY MISSING qqq.parquet

    config = {
        "universe": ["SPY", "IWM", "EFA", "EEM"],
        "data": {"start_date": "2004-01-01", "end_date": "2025-12-31"},
        "parameters": {"N": 5, "L": 60, "Z_entry": -2.0, "Z_exit": 0.0, "M": 10},
    }

    # Needs a real parquet structure for validate to read dates, let's just assert FileNotFoundError
    with pytest.raises(
        FileNotFoundError, match="Required research artifact is missing: .*qqq.parquet"
    ):
        validate_artifacts(tmp_path, config)


def test_holiday_requested_start_not_raw_data_start():
    # If REQUESTED_START is 2004-01-01 (holiday), RAW_DATA_START should be 2004-01-02
    start = "2004-01-01"
    # mock data index starting on 2004-01-02
    dates = pd.DatetimeIndex(["2004-01-02", "2004-01-05"])
    raw_data_start = dates[dates >= pd.Timestamp(start)][0]

    assert str(raw_data_start.date()) == "2004-01-02"
    assert str(raw_data_start.date()) != start
