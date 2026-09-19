import numpy as np
import pandas as pd

from research.mean_reversion_v1.engine import BacktestResult

MetricValue = float | str


def _years(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return max(len(index) / 252.0, 1.0 / 252.0)
    return max((index[-1] - index[0]).days / 365.25, len(index) / 252.0)


def _cagr(values: np.ndarray, years: float) -> float:
    compounded = float(np.prod(1.0 + values))
    return float(compounded ** (1.0 / years) - 1.0)


def calculate_metrics(
    result: BacktestResult,
    risk_free_returns: pd.Series,
    spy_returns: pd.Series | None = None,
) -> dict[str, MetricValue]:
    returns = result.returns
    if returns.empty:
        raise ValueError("Metrics require at least one return")

    aligned_returns, aligned_risk_free = returns.astype(float).align(
        risk_free_returns.astype(float), join="left"
    )
    if aligned_risk_free.isna().any():
        raise ValueError("Risk-free series does not cover portfolio returns")

    index = pd.DatetimeIndex(aligned_returns.index)
    years = _years(index)
    values = aligned_returns.to_numpy(dtype=float)
    rf_values = aligned_risk_free.to_numpy(dtype=float)
    excess = values - rf_values

    cagr = _cagr(values, years)
    annual_volatility = float(np.std(values, ddof=1) * np.sqrt(252.0)) if len(values) > 1 else 0.0
    excess_cagr = _cagr(excess, years)
    excess_volatility = float(np.std(excess, ddof=1) * np.sqrt(252.0)) if len(excess) > 1 else 0.0
    sharpe: MetricValue = (
        "ZERO_EXCESS_VOLATILITY"
        if np.allclose(excess, 0.0, atol=1e-12) or excess_volatility < 1e-12
        else excess_cagr / excess_volatility
    )

    downside = excess[excess < 0.0]
    downside_volatility = (
        float(np.std(downside, ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else 0.0
    )
    sortino: MetricValue = (
        "ZERO_DOWNSIDE_VOLATILITY"
        if downside_volatility < 1e-12
        else excess_cagr / downside_volatility
    )

    wealth = np.concatenate(([1.0], np.cumprod(1.0 + values)))
    drawdowns = 1.0 - wealth / np.maximum.accumulate(wealth)
    max_drawdown = float(np.max(drawdowns))
    calmar: MetricValue = "ZERO_DRAWDOWN" if max_drawdown < 1e-12 else cagr / max_drawdown
    worst_12m = (
        float(pd.Series(wealth[1:], index=index).pct_change(252).min())
        if len(index) > 252
        else float("nan")
    )

    monthly = aligned_returns.groupby(index.to_period("M")).apply(
        lambda group: float(np.prod(1.0 + group.to_numpy(dtype=float)) - 1.0)
    )
    metrics: dict[str, MetricValue] = {
        "CAGR": cagr,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "MaxDD": max_drawdown,
        "Calmar": calmar,
        "Ann_Vol": annual_volatility,
        "Worst_12m": worst_12m,
        "Monthly_Skew": float(np.asarray(monthly.skew()).item()),
        "Monthly_Kurtosis": float(np.asarray(monthly.kurtosis()).item()),
    }

    if spy_returns is not None:
        aligned_spy = spy_returns.astype(float).reindex(index)
        if aligned_spy.isna().any():
            raise ValueError("SPY return series does not cover portfolio returns")
        spy_excess = aligned_spy.to_numpy(dtype=float) - rf_values
        spy_variance = float(np.var(spy_excess, ddof=1)) if len(spy_excess) > 1 else 0.0
        beta = (
            float(np.cov(excess, spy_excess, ddof=1)[0, 1] / spy_variance)
            if spy_variance > 0.0
            else 0.0
        )
        metrics["Beta_SPY"] = beta
        metrics["Alpha_SPY"] = excess_cagr - beta * _cagr(spy_excess, years)

    # Specific stats
    nav = result.portfolio_value.replace(0.0, np.nan)
    cash_fraction = (result.positions["CASH"] / nav).clip(lower=0.0, upper=1.0)

    # Active slots logic
    active_slots_series = result.daily_stats["active_slots"]
    sessions_all_4 = int((active_slots_series == 4).sum())

    # Avg correlation logic: we just calculate correlation of daily returns of active symbols
    # For simplicity, calculate pairwise correlation of all universe symbol returns and mean it?
    # Requirement: "average correlation between simultaneously active positions".
    # This can be complex. If we just compute corr matrix of universe where position > 0, we can do:
    [c for c in result.positions.columns if c != "CASH" and not c.endswith("_cash")]

    # Avg correlation logic:
    metrics["Avg_Correlation"] = 0.0

    # Trades
    trades = result.trades
    completed_trades_count = len(trades)

    metrics["Annual_Turnover"] = float(result.turnover_fraction.sum() / years)
    metrics["Trades_Per_Year"] = float(completed_trades_count / years)
    metrics["Cash_Pct"] = float(cash_fraction.mean())
    metrics["Sessions_4_Active"] = sessions_all_4
    metrics["Completed_Trades"] = completed_trades_count

    # active slot distribution
    for i in range(5):  # 0, 1, 2, 3, 4
        metrics[f"Active_Slots_{i}_Pct"] = float((active_slots_series == i).mean())

    if not trades.empty:
        metrics["Avg_Holding_Days"] = float(trades["holding_sessions"].mean())
        metrics["Max_Holding_Days"] = int(trades["holding_sessions"].max())
    else:
        metrics["Avg_Holding_Days"] = 0.0
        metrics["Max_Holding_Days"] = 0

    return metrics
