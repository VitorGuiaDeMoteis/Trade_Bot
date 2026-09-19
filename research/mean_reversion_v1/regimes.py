import pandas as pd


def classify_regimes(spy_closes: pd.Series) -> pd.Series:
    """Returns a series of categorical strings: Bull, Bear, Chop."""
    ma200 = spy_closes.rolling(200).mean()
    spy_returns = spy_closes.pct_change(252)

    bull_mask = (spy_closes > ma200) & (spy_returns > 0)
    bear_mask = (spy_closes < ma200) & (spy_returns < 0)

    regimes = pd.Series("Chop", index=spy_closes.index)
    regimes[bull_mask] = "Bull"
    regimes[bear_mask] = "Bear"

    # NaN for warmup
    regimes.iloc[:200] = "Warmup"

    return regimes


def count_trades_by_regime(trades: pd.DataFrame, regimes: pd.Series) -> dict[str, int]:
    if trades.empty:
        return {"Bull": 0, "Bear": 0, "Chop": 0}

    counts = {"Bull": 0, "Bear": 0, "Chop": 0}
    for _, trade in trades.iterrows():
        entry_date = trade["entry_execution_date"]
        # Find closest regime on or before entry date
        idx = int(regimes.index.get_indexer(pd.Index([entry_date]), method="pad")[0])
        if idx >= 0:
            regime = regimes.iloc[idx]
            if pd.notna(regime) and regime in counts:
                counts[regime] += 1

    return counts
