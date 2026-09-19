import pandas as pd

from research.mean_reversion_v1.reporter import evaluate_combined_stress
from research.mean_reversion_v1.strategies import MeanReversionParams


def test_combined_stress_common_window():
    dates = pd.bdate_range("2010-01-01", "2010-02-28")
    data = pd.DataFrame(index=dates)
    data[("Close", "SPY")] = 100.0
    data[("Open", "SPY")] = 100.0
    data[("Close", "VOO")] = 100.0
    data[("Open", "VOO")] = 100.0
    data[("Close", "DTB3")] = 0.0

    rf = pd.Series(0.0, index=dates)
    spy = pd.Series(0.0, index=dates)

    params = MeanReversionParams(N=2, L=2, Z_entry=-2.0, Z_exit=0.0, M=10)

    # Prove it forces common window by using sub_start
    res = evaluate_combined_stress(
        data, ["SPY"], ["VOO"], params, dates[10], dates[-1], 10.0, 20.0, rf, spy
    )

    assert res["START_DATE"] == str(dates[10].date())
    assert res["END_DATE"] == str(dates[-1].date())
