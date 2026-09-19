import numpy as np
import pandas as pd
import pytest

from research.mean_reversion_v1.engine import run_backtest
from research.mean_reversion_v1.strategies import MeanReversionParams


@pytest.fixture
def mock_z_scores(monkeypatch):
    def fake_z(closes, N, L):
        idx = closes.index
        z = pd.Series(np.nan, index=idx)
        if len(idx) > 5:
            z.iloc[5] = -3.0
            z.iloc[6:] = -1.0
        return z

    monkeypatch.setattr("research.mean_reversion_v1.engine.compute_z_scores", fake_z)


def test_holding_period_bounded(mock_z_scores):
    dates = pd.bdate_range("2010-01-01", periods=20)
    data = pd.DataFrame(index=dates)
    sym = "SPY"
    data[("Close", sym)] = 100.0
    data[("Open", sym)] = 100.0
    data[("Close", "DTB3")] = 0.0

    params = MeanReversionParams(N=5, L=60, Z_entry=-2.0, Z_exit=0.0, M=10)
    res = run_backtest(data, [sym], params, dates[0], dates[-1], slots=1)

    trades = res.trades
    assert len(trades) == 1, "Should have exactly one completed trade"

    t = trades.iloc[0]

    assert t["entry_execution_date"] == dates[6]
    assert t["exit_execution_date"] == dates[16]
    assert t["holding_sessions"] == 10
