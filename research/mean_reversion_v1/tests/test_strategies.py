import numpy as np
import pandas as pd

from research.mean_reversion_v1.strategies import compute_z_scores


def test_z_score_excludes_current_day() -> None:
    # If N=1, L=3
    # r_N(t) = log(P_t/P_{t-1})
    # mu(t) = mean of r_N over t-3 to t-1.
    closes = pd.Series([10, 11, 10, 12, 11, 13, 14, 12, 10], dtype=float)
    z = compute_z_scores(closes, N=1, L=3)

    r = np.log(closes / closes.shift(1))

    # Check manual
    t = 4  # value=11
    # r(4) = log(11/12)
    # L=3 -> t-3, t-2, t-1 -> r(1), r(2), r(3)
    mu_manual = r.iloc[1:4].mean()  # type: ignore[attr-defined]
    std_manual = r.iloc[1:4].std()  # type: ignore[attr-defined]
    z_manual = (r.iloc[t] - mu_manual) / std_manual  # type: ignore[attr-defined]

    assert np.isclose(float(z.iloc[t]), z_manual)  # type: ignore[attr-defined]


def test_no_lookahead() -> None:
    # Changes in future prices should not affect past z-scores
    closes = pd.Series([10, 11, 10, 12, 11, 13, 14, 12, 10], dtype=float)
    z1 = compute_z_scores(closes, N=1, L=3)

    closes_alt = closes.copy()
    closes_alt.iloc[-1] = 1000  # change last value
    z2 = compute_z_scores(closes_alt, N=1, L=3)

    # Up to second to last, should be identical
    pd.testing.assert_series_equal(z1.iloc[:-1], z2.iloc[:-1])
