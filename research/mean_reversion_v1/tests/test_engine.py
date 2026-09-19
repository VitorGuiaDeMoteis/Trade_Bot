import pandas as pd

from research.mean_reversion_v1.engine import BacktestResult, run_backtest
from research.mean_reversion_v1.strategies import MeanReversionParams


def test_engine_can_run() -> None:
    dates = pd.bdate_range("2010-01-01", periods=20)
    data = pd.DataFrame(index=dates)
    data[("Close", "SPY")] = 100.0
    data[("Open", "SPY")] = 100.0
    data[("Close", "DTB3")] = 0.0

    params = MeanReversionParams(N=5, L=60, Z_entry=-2.0, Z_exit=0.0, M=10)
    res = run_backtest(data, ["SPY"], params, dates[0], dates[-1], slots=1)

    assert isinstance(res, BacktestResult)
