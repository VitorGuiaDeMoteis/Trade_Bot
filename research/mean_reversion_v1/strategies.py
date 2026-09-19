from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MeanReversionParams:
    N: int = 5
    L: int = 60
    Z_entry: float = -2.0
    Z_exit: float = 0.0
    M: int = 10


def compute_z_scores(closes: pd.Series, N: int, L: int) -> pd.Series:
    """
    r_N(t) = ln(P_adj(t) / P_adj(t-N))
    mu(t) = mean of r_N using [t-L, t-1]
    sigma(t) = std of r_N using [t-L, t-1]
    z(t) = (r_N(t) - mu(t)) / sigma(t)
    IMPORTANT: t is NOT in the window for mu/sigma.
    """
    # r_N(t)
    r_N = pd.Series(np.log(closes / closes.shift(N)))

    # We need to shift r_N by 1 so that at time t, we are looking at [t-L, t-1]
    # Then we do rolling window of size L
    shifted_r_N = r_N.shift(1)

    mu = shifted_r_N.rolling(window=L, min_periods=L).mean()
    # pandas uses ddof=1 by default for std, which is standard sample std
    sigma = shifted_r_N.rolling(window=L, min_periods=L).std()

    z = (r_N - mu) / sigma
    return z
