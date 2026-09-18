"""Period-restricted experiment and robustness runners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.momentum_v1.accrual import compute_daily_risk_free_return
from research.momentum_v1.bootstrap import block_bootstrap
from research.momentum_v1.data import SUBSTITUTIONS
from research.momentum_v1.engine import BacktestResult, RebalanceDay, run_backtest
from research.momentum_v1.metrics import MetricValue, summarize_result
from research.momentum_v1.strategies import (
    AM_PRIMARY,
    AM_SENSITIVITIES,
    B0,
    B1,
    B2,
    RAM_PRIMARY,
    RAM_SENSITIVITIES,
    StrategySpec,
)

MetricTable = dict[str, dict[str, MetricValue]]


@dataclass(frozen=True)
class AnalysisBundle:
    metrics: MetricTable
    results: dict[str, BacktestResult]


def _period(config: Mapping[str, object], name: str) -> tuple[str, str]:
    periods = config.get("periods")
    if not isinstance(periods, dict) or not isinstance(periods.get(name), dict):
        raise KeyError(f"Missing configured period: {name}")
    selected = periods[name]
    return str(selected["start"]), str(selected["end"])


def assert_public_period(config: Mapping[str, object], name: str, start: str, end: str) -> None:
    if name not in {"development", "diagnostic"}:
        raise PermissionError("Only development and burned diagnostic periods are public before seal")
    expected = _period(config, name)
    if (start, end) != expected:
        raise PermissionError(f"{name} must use its exact pre-registered bounds")
    holdout_start, _ = _period(config, "holdout")
    if pd.Timestamp(end) >= pd.Timestamp(holdout_start):
        raise PermissionError("HOLDOUT_FIREWALL_VIOLATION")


def run_core(
    data: pd.DataFrame,
    universe: list[str],
    start: str,
    end: str,
    *,
    cost_bps: float = 5.0,
) -> AnalysisBundle:
    specs = {"B0": B0, "B1": B1, "B2": B2, "AM": AM_PRIMARY, "RAM": RAM_PRIMARY}
    results = {name: run_backtest(data, universe, spec, start, end, cost_bps=cost_bps) for name, spec in specs.items()}
    metrics: MetricTable = {}
    for name, result in results.items():
        risk_free = compute_daily_risk_free_return(data, pd.DatetimeIndex(result.returns.index))
        metrics[name] = summarize_result(result, risk_free)
    return AnalysisBundle(metrics, results)


def run_public_period(data: pd.DataFrame, config: Mapping[str, object], name: str) -> AnalysisBundle:
    start, end = _period(config, name)
    assert_public_period(config, name, start, end)
    universe_value = config.get("universe")
    if not isinstance(universe_value, list):
        raise TypeError("config.universe must be a list")
    return run_core(data, [str(symbol) for symbol in universe_value], start, end)


def _metrics_for_spec(
    data: pd.DataFrame,
    universe: list[str],
    spec: StrategySpec,
    start: str,
    end: str,
    *,
    cost_bps: float = 5.0,
    rebalance_day: RebalanceDay = "last",
) -> dict[str, MetricValue]:
    result = run_backtest(data, universe, spec, start, end, cost_bps=cost_bps, rebalance_day=rebalance_day)
    risk_free = compute_daily_risk_free_return(data, pd.DatetimeIndex(result.returns.index))
    return summarize_result(result, risk_free)


def run_sensitivity_matrix(data: pd.DataFrame, universe: list[str], start: str, end: str) -> dict[str, object]:
    am = {name: _metrics_for_spec(data, universe, spec, start, end) for name, spec in AM_SENSITIVITIES.items()}
    ram = {name: _metrics_for_spec(data, universe, spec, start, end) for name, spec in RAM_SENSITIVITIES.items()}
    costs = {
        str(int(cost)): {
            "AM": _metrics_for_spec(data, universe, AM_PRIMARY, start, end, cost_bps=cost),
            "B1": _metrics_for_spec(data, universe, B1, start, end, cost_bps=cost),
        }
        for cost in (5.0, 10.0, 15.0)
    }
    lookbacks = {
        str(months): _metrics_for_spec(data, universe, StrategySpec(f"AM_{months}", "am", lookback_months=months), start, end)
        for months in (10, 12, 14)
    }
    timing_values: tuple[RebalanceDay, ...] = ("first", "penultimate", "last")
    timings = {timing: _metrics_for_spec(data, universe, AM_PRIMARY, start, end, rebalance_day=timing) for timing in timing_values}
    leave_one_out = {symbol: _metrics_for_spec(data, [item for item in universe if item != symbol], AM_PRIMARY, start, end) for symbol in universe}
    return {"am": am, "ram": ram, "costs": costs, "lookbacks": lookbacks, "timings": timings, "leave_one_out": leave_one_out}


def _common_substitution_data(
    primary: pd.DataFrame,
    substitutes: pd.DataFrame,
    original: str,
    replacement: str,
) -> pd.DataFrame:
    required = [("Open", replacement), ("Close", replacement)]
    if any(column not in substitutes.columns for column in required):
        raise ValueError(f"Substitution data missing for {replacement}")
    combined = primary.copy()
    combined[("Open", replacement)] = substitutes[("Open", replacement)].reindex(combined.index)
    combined[("Close", replacement)] = substitutes[("Close", replacement)].reindex(combined.index)
    valid = combined[("Open", replacement)].notna() & combined[("Close", replacement)].notna()
    valid &= combined[("Open", original)].notna() & combined[("Close", original)].notna()
    return combined.iloc[np.flatnonzero(valid.to_numpy(dtype=bool))]


def run_substitutions(
    primary: pd.DataFrame,
    substitutes: pd.DataFrame,
    universe: list[str],
    start: str,
    end: str,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for original, replacement in SUBSTITUTIONS.items():
        common = _common_substitution_data(primary, substitutes, original, replacement)
        common_start = max(pd.Timestamp(start), pd.Timestamp(common.index.min()) + pd.DateOffset(months=12))
        common_end = min(pd.Timestamp(end), pd.Timestamp(common.index.max()))
        if common_start > common_end:
            raise ValueError(f"No common overlap for {original}->{replacement}")
        baseline_universe = universe
        replacement_universe = [replacement if symbol == original else symbol for symbol in universe]
        window_start, window_end = common_start.strftime("%Y-%m-%d"), common_end.strftime("%Y-%m-%d")
        output[f"{original}->{replacement}"] = {
            "common_start": window_start,
            "common_end": window_end,
            "AM_baseline": _metrics_for_spec(common, baseline_universe, AM_PRIMARY, window_start, window_end),
            "AM_substitution": _metrics_for_spec(common, replacement_universe, AM_PRIMARY, window_start, window_end),
            "RAM_baseline": _metrics_for_spec(common, baseline_universe, RAM_PRIMARY, window_start, window_end),
            "RAM_substitution": _metrics_for_spec(common, replacement_universe, RAM_PRIMARY, window_start, window_end),
        }
    return output


def classify_monthly_regimes(data: pd.DataFrame, start: str, end: str) -> pd.Series:
    spy = data[("Close", "SPY")].astype(float)
    ma200 = spy.rolling(200, min_periods=200).mean()
    return_12m = spy.pct_change(252)
    frame = pd.DataFrame({"spy": spy, "ma200": ma200, "return_12m": return_12m})
    frame = frame.loc[frame.index <= pd.Timestamp(end)]
    monthly = frame.resample("ME").last()
    monthly = monthly.loc[(monthly.index >= pd.Timestamp(start)) & (monthly.index <= pd.Timestamp(end))]
    regimes = pd.Series("Chop", index=monthly.index, dtype="object")
    regimes.loc[(monthly["spy"] > monthly["ma200"]) & (monthly["return_12m"] > 0.0)] = "Bull"
    regimes.loc[(monthly["spy"] < monthly["ma200"]) & (monthly["return_12m"] < 0.0)] = "Bear"
    return regimes


def regime_metrics(data: pd.DataFrame, bundle: AnalysisBundle, start: str, end: str) -> dict[str, dict[str, dict[str, MetricValue]]]:
    regimes = classify_monthly_regimes(data, start, end)
    output: dict[str, dict[str, dict[str, MetricValue]]] = {}
    for strategy_name, result in bundle.results.items():
        monthly_returns = result.returns.resample("ME").apply(lambda values: float(np.prod(1.0 + values.to_numpy(dtype=float)) - 1.0))
        daily_rf = compute_daily_risk_free_return(data, pd.DatetimeIndex(result.returns.index))
        monthly_rf = daily_rf.resample("ME").apply(lambda values: float(np.prod(1.0 + values.to_numpy(dtype=float)) - 1.0))
        monthly_positions = result.positions.resample("ME").last()
        monthly_nav = result.portfolio_value.resample("ME").last()
        strategy_output: dict[str, dict[str, MetricValue]] = {}
        for regime in ("Bull", "Bear", "Chop"):
            dates = regimes.index[regimes == regime].intersection(monthly_returns.index)
            selected = monthly_returns.loc[dates]
            if selected.empty:
                strategy_output[regime] = {"Months": 0.0}
                continue
            selected_rf = monthly_rf.loc[dates]
            values = selected.to_numpy(dtype=float)
            years = len(values) / 12.0
            cagr = float(np.prod(1.0 + values) ** (1.0 / years) - 1.0)
            excess = values - selected_rf.to_numpy(dtype=float)
            volatility = float(np.std(excess, ddof=1) * np.sqrt(12.0)) if len(excess) > 1 else 0.0
            wealth = np.concatenate(([1.0], np.cumprod(1.0 + values)))
            max_drawdown = float(np.max(1.0 - wealth / np.maximum.accumulate(wealth)))
            cash = (monthly_positions.loc[dates, "CASH"] / monthly_nav.loc[dates]).mean()
            strategy_output[regime] = {
                "Months": float(len(values)),
                "CAGR": cagr,
                "Sharpe": "ZERO_EXCESS_VOLATILITY" if volatility < 1e-12 else float((np.mean(excess) * 12.0) / volatility),
                "MaxDD": max_drawdown,
                "Cash_Pct": float(cash),
                "Exposure_Pct": float(1.0 - cash),
            }
        output[strategy_name] = strategy_output
    return output


def confidence_intervals(bundle: AnalysisBundle, context_hash: str, samples: int, block_size_months: int) -> dict[str, dict[str, list[float]]]:
    output: dict[str, dict[str, list[float]]] = {}
    for name, result in bundle.results.items():
        bootstrap = block_bootstrap(result.returns, f"{context_hash}:{name}", samples, block_size_months)
        output[name] = {column: [float(bootstrap[column].quantile(0.025)), float(bootstrap[column].quantile(0.975))] for column in bootstrap.columns}
    return output
