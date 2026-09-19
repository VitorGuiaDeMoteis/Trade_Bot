import numpy as np
import pandas as pd

from research.mean_reversion_v1.regimes import classify_regimes, count_trades_by_regime


def test_regime_completed_trades_sum():
    dates = pd.bdate_range("2010-01-01", periods=300)

    spy = pd.Series(np.linspace(100, 200, 300), index=dates)
    regimes = classify_regimes(spy)

    # Create synthetic trades dataframe
    trades = pd.DataFrame(
        [
            {"entry_execution_date": dates[210]},
            {"entry_execution_date": dates[250]},
            {"entry_execution_date": dates[280]},
        ]
    )

    counts = count_trades_by_regime(trades, regimes)
    assert sum(counts.values()) == len(trades), "regime_completed_trades_sum == completed_trades"
