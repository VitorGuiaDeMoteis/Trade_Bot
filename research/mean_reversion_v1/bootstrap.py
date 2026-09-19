import hashlib

import numpy as np
import pandas as pd


def deterministic_seed(context_hash: str) -> int:
    return int(hashlib.sha256(context_hash.encode("utf-8")).hexdigest()[:16], 16) % (2**32)


def compute_sharpe(sample: np.ndarray, rf_sample: np.ndarray) -> float:
    excess = sample - rf_sample
    mean_excess = np.mean(excess) * 252
    std_excess = np.std(excess, ddof=1) * np.sqrt(252)
    if std_excess < 1e-12:
        return 0.0
    return float(mean_excess / std_excess)


def compute_maxdd(sample: np.ndarray) -> float:
    wealth = np.concatenate(([1.0], np.cumprod(1.0 + sample)))
    drawdowns = 1.0 - wealth / np.maximum.accumulate(wealth)
    return float(np.max(drawdowns))


def block_bootstrap(
    returns: pd.Series,
    risk_free: pd.Series,
    context_hash: str,
    n_samples: int = 5000,
    block_sizes: tuple[int, ...] = (10, 60),
) -> dict[int, pd.DataFrame]:

    aligned_ret, aligned_rf = returns.align(risk_free, join="left")
    values = aligned_ret.to_numpy(dtype=float)
    rf_values = aligned_rf.to_numpy(dtype=float)

    results = {}
    generator = np.random.default_rng(deterministic_seed(context_hash))

    for block_size in block_sizes:
        if len(values) < block_size:
            results[block_size] = pd.DataFrame(columns=["Sharpe", "MaxDD"])
            continue

        blocks_ret = [values[i : i + block_size] for i in range(len(values) - block_size + 1)]
        blocks_rf = [rf_values[i : i + block_size] for i in range(len(rf_values) - block_size + 1)]

        draws = int(np.ceil(len(values) / block_size))

        rows = []
        for _ in range(n_samples):
            chosen = generator.integers(0, len(blocks_ret), size=draws)

            sample_ret = np.concatenate([blocks_ret[i] for i in chosen])[: len(values)]
            sample_rf = np.concatenate([blocks_rf[i] for i in chosen])[: len(rf_values)]

            rows.append(
                {
                    "Sharpe": compute_sharpe(sample_ret, sample_rf),
                    "MaxDD": compute_maxdd(sample_ret),
                }
            )

        results[block_size] = pd.DataFrame(rows)

    return results
