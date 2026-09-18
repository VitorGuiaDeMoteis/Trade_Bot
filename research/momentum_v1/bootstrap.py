"""Deterministic monthly block bootstrap."""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd


def deterministic_seed(context_hash: str) -> int:
    return int(hashlib.sha256(context_hash.encode("utf-8")).hexdigest()[:16], 16) % (2**32)


def block_bootstrap(
    returns: pd.Series,
    context_hash: str,
    n_samples: int = 5000,
    block_size_months: int = 6,
) -> pd.DataFrame:
    if n_samples <= 0 or block_size_months <= 0:
        raise ValueError("Bootstrap parameters must be positive")
    index = pd.DatetimeIndex(returns.index)
    monthly = returns.astype(float).groupby(index.to_period("M")).apply(lambda group: float(np.prod(1.0 + group.to_numpy()) - 1.0))
    values = monthly.to_numpy(dtype=float)
    if len(values) < block_size_months:
        return pd.DataFrame(columns=["CAGR", "Ann_Vol", "MaxDD"])
    blocks = [values[position : position + block_size_months] for position in range(len(values) - block_size_months + 1)]
    draws = math.ceil(len(values) / block_size_months)
    generator = np.random.default_rng(deterministic_seed(context_hash))
    rows: list[dict[str, float]] = []
    for _ in range(n_samples):
        chosen = generator.integers(0, len(blocks), size=draws)
        sample = np.concatenate([blocks[int(position)] for position in chosen])[: len(values)]
        wealth = np.concatenate(([1.0], np.cumprod(1.0 + sample)))
        rows.append(
            {
                "CAGR": float(wealth[-1] ** (12.0 / len(sample)) - 1.0),
                "Ann_Vol": float(np.std(sample, ddof=1) * np.sqrt(12.0)),
                "MaxDD": float(np.max(1.0 - wealth / np.maximum.accumulate(wealth))),
            }
        )
    return pd.DataFrame(rows)
