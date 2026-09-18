"""Deterministic close-signal/next-open portfolio engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd

from research.momentum_v1.accrual import compute_daily_risk_free_return
from research.momentum_v1.strategies import StrategySpec, signal_weights

SignalFunction = Callable[[pd.DataFrame, pd.Timestamp, list[str]], dict[str, float]]
RebalanceDay = Literal["first", "penultimate", "last"]


def _numeric(value: object, *, label: str) -> float:
    if not isinstance(value, Real):
        raise TypeError(f"{label} must be numeric")
    return float(value)


@dataclass(frozen=True)
class BacktestResult:
    returns: pd.Series
    portfolio_value: pd.Series
    turnover: pd.Series
    turnover_fraction: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    target_weights: pd.DataFrame


def _rebalance_signals(index: pd.DatetimeIndex, frequency: str, day: RebalanceDay) -> list[pd.Timestamp]:
    periods = index.to_period("Q" if frequency == "Q" else "M")
    frame = pd.DataFrame({"date": index, "period": periods})
    selected: list[pd.Timestamp] = []
    for _, group in frame.groupby("period", sort=True):
        dates = pd.DatetimeIndex(group["date"])
        if day == "first":
            selected.append(pd.Timestamp(dates[0]))
        elif day == "penultimate":
            selected.append(pd.Timestamp(dates[-2] if len(dates) > 1 else dates[-1]))
        else:
            selected.append(pd.Timestamp(dates[-1]))
    return selected


def execution_schedule(
    index: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
    frequency: str,
    day: RebalanceDay,
) -> dict[pd.Timestamp, pd.Timestamp]:
    output: dict[pd.Timestamp, pd.Timestamp] = {}
    for signal_date in _rebalance_signals(index[index <= end], frequency, day):
        position = int(index.searchsorted(signal_date))
        if position + 1 >= len(index):
            continue
        execution_date = pd.Timestamp(index[position + 1])
        if start <= execution_date <= end:
            output[execution_date] = signal_date
    return output


def _validate_weights(weights: dict[str, float], universe: list[str]) -> None:
    unknown = set(weights) - set(universe)
    if unknown:
        raise ValueError(f"Signal returned symbols outside the universe: {sorted(unknown)}")
    if any(not np.isfinite(value) or value < 0.0 for value in weights.values()):
        raise ValueError("Target weights must be finite and non-negative")
    if sum(weights.values()) > 1.0 + 1e-12:
        raise ValueError("Target weights exceed 100%")


def _post_cost_nav(gross_nav: float, weights: dict[str, float], current: dict[str, float], side_rate: float) -> tuple[float, float]:
    post_nav = gross_nav
    for _ in range(20):
        turnover = sum(abs(post_nav * weights.get(symbol, 0.0) - value) for symbol, value in current.items())
        updated = gross_nav - turnover * side_rate
        if abs(updated - post_nav) < 1e-9:
            return updated, turnover
        post_nav = updated
    turnover = sum(abs(post_nav * weights.get(symbol, 0.0) - value) for symbol, value in current.items())
    return post_nav, turnover


def run_backtest(
    data: pd.DataFrame,
    universe: list[str],
    strategy: StrategySpec | SignalFunction,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    initial_capital: float = 10_000_000.0,
    cost_bps: float = 5.0,
    rebalance_freq: str | None = None,
    rebalance_day: RebalanceDay = "last",
    *,
    zero_cash: bool = False,
) -> BacktestResult:
    index = pd.DatetimeIndex(data.index).tz_localize(None).sort_values()
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Market sessions must be sorted and unique")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    sessions = index[(index >= start) & (index <= end)]
    if sessions.empty:
        raise ValueError("No market sessions in requested backtest period")

    frequency = rebalance_freq or (strategy.rebalance_freq if isinstance(strategy, StrategySpec) else "M")
    schedule = execution_schedule(index, start, end, frequency, rebalance_day)
    targets: dict[pd.Timestamp, dict[str, float]] = {}
    for execution_date, signal_date in schedule.items():
        visible = data.loc[:signal_date]
        weights = (
            signal_weights(visible, signal_date, universe, strategy)
            if isinstance(strategy, StrategySpec)
            else strategy(visible, signal_date, universe)
        )
        _validate_weights(weights, universe)
        targets[execution_date] = weights

    risk_free = compute_daily_risk_free_return(data, index, zero_cash=zero_cash)
    holdings = {symbol: 0.0 for symbol in universe}
    cash = float(initial_capital)
    values: list[float] = []
    turnover_values: list[float] = []
    turnover_fractions: list[float] = []
    position_rows: list[dict[str, float]] = []
    target_rows: list[dict[str, float]] = []
    trade_rows: list[dict[str, object]] = []
    side_rate = cost_bps / 2.0 / 10_000.0

    for offset, date in enumerate(sessions):
        date = pd.Timestamp(date)
        is_execution = date in targets
        if offset > 0:
            previous = pd.Timestamp(sessions[offset - 1])
            cash *= 1.0 + float(risk_free.loc[date])
            for symbol in universe:
                previous_close = _numeric(data.at[previous, ("Close", symbol)], label=f"{symbol} previous close")
                current_price = _numeric(data.at[date, ("Open" if is_execution else "Close", symbol)], label=f"{symbol} current price")
                if not np.isfinite(previous_close) or not np.isfinite(current_price) or previous_close <= 0.0:
                    raise ValueError(f"Invalid price for {symbol} on {date.date()}")
                holdings[symbol] *= current_price / previous_close

        turnover = 0.0
        turnover_fraction = 0.0
        weights = targets.get(date, {})
        if is_execution:
            gross_nav = cash + sum(holdings.values())
            post_nav, turnover = _post_cost_nav(gross_nav, weights, holdings, side_rate)
            for symbol in universe:
                target_value = post_nav * weights.get(symbol, 0.0)
                delta = target_value - holdings[symbol]
                if abs(delta) > 1e-8:
                    trade_rows.append({"date": date, "symbol": symbol, "notional": delta, "abs_notional": abs(delta)})
                holdings[symbol] = target_value
            cash = post_nav * (1.0 - sum(weights.values()))
            turnover_fraction = turnover / gross_nav if gross_nav > 0.0 else 0.0
            for symbol in universe:
                open_price = _numeric(data.at[date, ("Open", symbol)], label=f"{symbol} open")
                close_price = _numeric(data.at[date, ("Close", symbol)], label=f"{symbol} close")
                if not np.isfinite(open_price) or not np.isfinite(close_price) or open_price <= 0.0:
                    raise ValueError(f"Invalid execution price for {symbol} on {date.date()}")
                holdings[symbol] *= close_price / open_price

        nav = cash + sum(holdings.values())
        values.append(nav)
        turnover_values.append(turnover)
        turnover_fractions.append(turnover_fraction)
        position_rows.append({**holdings, "CASH": cash})
        target_rows.append({symbol: weights.get(symbol, 0.0) for symbol in universe} if is_execution else {symbol: np.nan for symbol in universe})

    portfolio_value = pd.Series(values, index=sessions, name="portfolio_value", dtype=float)
    returns = portfolio_value.pct_change()
    returns.iloc[0] = portfolio_value.iloc[0] / initial_capital - 1.0
    positions = pd.DataFrame(position_rows, index=sessions, dtype=float)
    trades = pd.DataFrame(trade_rows, columns=["date", "symbol", "notional", "abs_notional"])
    return BacktestResult(
        returns=returns.astype(float),
        portfolio_value=portfolio_value,
        turnover=pd.Series(turnover_values, index=sessions, name="turnover", dtype=float),
        turnover_fraction=pd.Series(turnover_fractions, index=sessions, name="turnover_fraction", dtype=float),
        positions=positions,
        trades=trades,
        target_weights=pd.DataFrame(target_rows, index=sessions, dtype=float),
    )
