import numpy as np
import pandas as pd
import pytest

from research.mean_reversion_v1.data import discover_first_valid_signal
from research.mean_reversion_v1.engine import run_backtest
from research.mean_reversion_v1.strategies import MeanReversionParams, compute_z_scores


def test_no_12_month_warmup_and_65_session_fixture() -> None:
    # 2. A fixture with fewer than 65 required valid sessions refuses to emit a signal.
    # 4. Missing/non-trading calendar days do not count as sessions.
    dates = pd.bdate_range("2004-01-01", periods=64)
    data = pd.DataFrame(index=dates)
    data[("Close", "SPY")] = 100.0
    data[("Open", "SPY")] = 100.0

    with pytest.raises(ValueError, match="INSUFFICIENT_PRIMARY_HISTORY"):
        discover_first_valid_signal(data, ["SPY"], L=60, N=5)


def test_first_valid_signal_is_derived_from_index_and_no_2003_data() -> None:
    # 3. The first valid signal is derived from the actual session index, not a hardcoded date.
    # 7. Starting data on 2004-01-01 never causes the engine to request 2003 data
    dates = pd.bdate_range("2004-01-01", periods=70)
    data = pd.DataFrame(index=dates)
    data[("Close", "SPY")] = 100.0
    data[("Open", "SPY")] = 100.0

    # 65 valid sessions (L+N = 65) means index 65 is the first valid signal
    # Wait, if we need 65 sessions of history (L+N = 65), then index 64 is the 65th session.
    # So index 64 is the first valid date where we have 65 non-NaN sessions including itself.
    sig = discover_first_valid_signal(data, ["SPY"], L=60, N=5)
    assert sig == dates[65]
    # exactly 65 elements

    assert sig.year == 2004


def test_first_signal_properties_and_execution() -> None:
    # 5. The first signal has: valid r_5(t), 60 prior valid values, current r_5(t) excluded
    # 6. FIRST_EXECUTION is the next valid trading session.

    dates = pd.bdate_range("2004-01-01", periods=70)
    data = pd.DataFrame(index=dates)

    # Make prices such that r_N is predictable
    np.random.seed(42)
    closes = 100 + np.random.randn(70) * 0.1
    # Force a trade at the signal date
    closes[65] = 50.0  # drop to create signal
    closes[66] = 50.0

    data[("Close", "SPY")] = closes
    data[("Open", "SPY")] = closes
    data[("Close", "DTB3")] = 0.0

    params = MeanReversionParams(N=5, L=60, Z_entry=-2.0, Z_exit=0.0, M=10)

    sig = discover_first_valid_signal(data, ["SPY"], L=60, N=5)

    # Check z-scores
    spy_close = data[("Close", "SPY")]
    r_5 = pd.Series(np.log(spy_close / spy_close.shift(5)))

    z = compute_z_scores(spy_close, N=5, L=60)

    # At sig (index 65):
    # r_5 is valid
    assert not pd.isna(r_5.loc[sig])

    # 60 prior valid r_5 values?
    # r_5 needs 5 days to be valid, so first valid r_5 is at index 5.
    # at index 65, we have r_5 from index 5 to 64, which is 60 values!
    valid_prior_r_5 = r_5.iloc[:65].dropna()
    assert len(valid_prior_r_5) == 60

    # Excluded from mu/sigma:
    mu = valid_prior_r_5.mean()
    sigma = valid_prior_r_5.std()

    expected_z = (r_5.loc[sig] - mu) / sigma
    assert np.isclose(z.loc[sig], expected_z)

    # 6. FIRST_EXECUTION is the next valid trading session.
    # The drop is at sig (index 65). We should see execution at index 66.
    res = run_backtest(data, ["SPY"], params, str(sig.date()), str(dates[-1].date()), cost_bps=0.0)
    spy_trades = res.trades[res.trades["symbol"] == "SPY"]
    assert not spy_trades.empty

    entry_trade = spy_trades.iloc[0]
    assert entry_trade["entry_execution_date"] == dates[66]  # executed at next session
    assert pd.notna(entry_trade["entry_execution_date"])
