"""Performance metrics with explicit zero-volatility status values."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.momentum_v1.engine import BacktestResult

type MetricValue = float | str


def _years(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return max(len(index) / 252.0, 1.0 / 252.0)
    return max((index[-1] - index[0]).days / 365.25, len(index) / 252.0)


def _cagr(values: np.ndarray, years: float) -> float:
    compounded = float(np.prod(1.0 + values))
    return float(compounded ** (1.0 / years) - 1.0)


def calculate_metrics(
    returns: pd.Series,
    risk_free_returns: pd.Series,
    spy_returns: pd.Series | None = None,
) -> dict[str, MetricValue]:
    if returns.empty:
        raise ValueError("Metrics require at least one return")
    aligned_returns, aligned_risk_free = returns.astype(float).align(risk_free_returns.astype(float), join="left")
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
        "ZERO_EXCESS_VOLATILITY" if np.allclose(excess, 0.0, atol=1e-12) or excess_volatility < 1e-12 else excess_cagr / excess_volatility
    )

    downside = excess[excess < 0.0]
    downside_volatility = float(np.std(downside, ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else 0.0
    sortino: MetricValue = "ZERO_DOWNSIDE_VOLATILITY" if downside_volatility < 1e-12 else excess_cagr / downside_volatility

    wealth = np.concatenate(([1.0], np.cumprod(1.0 + values)))
    drawdowns = 1.0 - wealth / np.maximum.accumulate(wealth)
    max_drawdown = float(np.max(drawdowns))
    calmar: MetricValue = "ZERO_DRAWDOWN" if max_drawdown < 1e-12 else cagr / max_drawdown
    worst_12m = float(pd.Series(wealth[1:], index=index).pct_change(252).min()) if len(index) > 252 else float("nan")

    monthly = aligned_returns.groupby(index.to_period("M")).apply(lambda group: float(np.prod(1.0 + group.to_numpy(dtype=float)) - 1.0))
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
        beta = float(np.cov(excess, spy_excess, ddof=1)[0, 1] / spy_variance) if spy_variance > 0.0 else 0.0
        metrics["Beta_SPY"] = beta
        metrics["Alpha_SPY"] = excess_cagr - beta * _cagr(spy_excess, years)
    return metrics


def summarize_result(result: BacktestResult, risk_free_returns: pd.Series, spy_returns: pd.Series | None = None) -> dict[str, MetricValue]:
    metrics = calculate_metrics(result.returns, risk_free_returns, spy_returns)
    years = _years(pd.DatetimeIndex(result.returns.index))
    nav = result.portfolio_value.replace(0.0, np.nan)
    cash_fraction = (result.positions["CASH"] / nav).clip(lower=0.0, upper=1.0)
    asset_positions = result.positions.drop(columns="CASH")
    metrics.update(
        {
            "Annual_Turnover": float(result.turnover_fraction.sum() / years),
            "Trades_Per_Year": float(len(result.trades) / years),
            "Cash_Pct": float(cash_fraction.mean()),
            "Average_Positions": float((asset_positions.abs() > 1e-8).sum(axis=1).mean()),
        }
    )
    return metrics
