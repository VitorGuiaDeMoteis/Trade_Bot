"""Pre-registered Momentum V1.3 strategy definitions."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd

from research.momentum_v1.accrual import compound_period_return, compute_daily_risk_free_return

StrategyKind = Literal["cash", "equal_weight", "fixed_weight", "am", "ram"]
RebalanceFrequency = Literal["M", "Q"]


class InsufficientHistoryError(ValueError):
    """Raised when a signal cannot be constructed without inventing history."""


def _numeric(value: object, *, label: str) -> float:
    if not isinstance(value, Real):
        raise TypeError(f"{label} must be numeric")
    return float(value)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    kind: StrategyKind
    lookback_months: int = 12
    skip_months: int = 0
    use_tbill: bool = True
    k: int = 3
    rebalance_freq: RebalanceFrequency = "M"
    fixed_weights: tuple[tuple[str, float], ...] = ()


B0 = StrategySpec("B0", "cash")
B1 = StrategySpec("B1", "equal_weight")
B2 = StrategySpec("B2", "fixed_weight", fixed_weights=(("SPY", 0.6), ("TLT", 0.4)))
AM_PRIMARY = StrategySpec("AM", "am")
RAM_PRIMARY = StrategySpec("RAM", "ram", k=3)

AM_SENSITIVITIES: dict[str, StrategySpec] = {
    "A1": StrategySpec("A1", "am", lookback_months=6),
    "A2": StrategySpec("A2", "am", lookback_months=12, skip_months=1),
    "A3": StrategySpec("A3", "am", lookback_months=12, use_tbill=False),
    "A4": StrategySpec("A4", "am", lookback_months=12, rebalance_freq="Q"),
}

RAM_SENSITIVITIES: dict[str, StrategySpec] = {
    "R1": StrategySpec("R1", "ram", k=2),
    "R2": StrategySpec("R2", "ram", k=4),
    "R3": StrategySpec("R3", "ram", lookback_months=6, k=3),
    "R4": StrategySpec("R4", "ram", lookback_months=12, skip_months=1, k=3),
    "R5": StrategySpec("R5", "ram", lookback_months=12, k=3, rebalance_freq="Q"),
}


def _session_at_or_before(index: pd.DatetimeIndex, target: pd.Timestamp) -> pd.Timestamp:
    position = int(index.searchsorted(target, side="right")) - 1
    if position < 0:
        raise InsufficientHistoryError(f"No market session exists at or before {target.date()}")
    return pd.Timestamp(index[position])


def momentum_returns(
    data: pd.DataFrame,
    signal_date: pd.Timestamp,
    universe: list[str],
    *,
    lookback_months: int,
    skip_months: int,
) -> tuple[dict[str, float], pd.Timestamp, pd.Timestamp]:
    index = pd.DatetimeIndex(data.index).tz_localize(None).sort_values()
    signal_date = pd.Timestamp(signal_date).tz_localize(None)
    if signal_date not in index:
        raise ValueError("Signal date is not a valid market session")
    end_session = _session_at_or_before(index, signal_date - pd.DateOffset(months=skip_months))
    start_target = end_session - pd.DateOffset(months=lookback_months)
    start_session = _session_at_or_before(index, start_target)
    if start_session > start_target:
        raise InsufficientHistoryError("Lookback would require future data")

    output: dict[str, float] = {}
    for symbol in universe:
        column = ("Close", symbol)
        if column not in data.columns:
            raise InsufficientHistoryError(f"Missing close series for {symbol}")
        start_price = _numeric(data.at[start_session, column], label=f"{symbol} start price")
        end_price = _numeric(data.at[end_session, column], label=f"{symbol} end price")
        if not np.isfinite(start_price) or not np.isfinite(end_price) or start_price <= 0.0:
            raise InsufficientHistoryError(f"Invalid {symbol} history for signal {signal_date.date()}")
        output[symbol] = end_price / start_price - 1.0
    return output, start_session, end_session


def signal_weights(data: pd.DataFrame, signal_date: pd.Timestamp, universe: list[str], spec: StrategySpec) -> dict[str, float]:
    if spec.kind == "cash":
        return {}
    if spec.kind == "equal_weight":
        weight = 1.0 / len(universe)
        return {symbol: weight for symbol in universe}
    if spec.kind == "fixed_weight":
        return dict(spec.fixed_weights)

    returns, start_session, end_session = momentum_returns(
        data,
        signal_date,
        universe,
        lookback_months=spec.lookback_months,
        skip_months=spec.skip_months,
    )
    if spec.use_tbill:
        sessions = pd.DatetimeIndex(data.index).tz_localize(None)
        risk_free = compute_daily_risk_free_return(data, sessions)
        threshold = compound_period_return(risk_free, start_session, end_session)
    else:
        threshold = 0.0
    eligible = {symbol: value for symbol, value in returns.items() if value > threshold}
    if not eligible:
        return {}
    if spec.kind == "am":
        weight = 1.0 / len(eligible)
        return {symbol: weight for symbol in eligible}
    ranked = sorted(eligible, key=lambda symbol: (-eligible[symbol], symbol))[: spec.k]
    return {symbol: 1.0 / spec.k for symbol in ranked}


def strategy_b0(data: pd.DataFrame, date: pd.Timestamp, universe: list[str]) -> dict[str, float]:
    return signal_weights(data, date, universe, B0)


def strategy_b1(data: pd.DataFrame, date: pd.Timestamp, universe: list[str]) -> dict[str, float]:
    return signal_weights(data, date, universe, B1)


def strategy_b2(data: pd.DataFrame, date: pd.Timestamp, universe: list[str]) -> dict[str, float]:
    return signal_weights(data, date, universe, B2)


def strategy_primary_am(
    data: pd.DataFrame,
    date: pd.Timestamp,
    universe: list[str],
    lookback_months: int = 12,
    skip_months: int = 0,
    use_tbill: bool = True,
) -> dict[str, float]:
    spec = StrategySpec("AM", "am", lookback_months, skip_months, use_tbill)
    return signal_weights(data, date, universe, spec)


def strategy_primary_ram(
    data: pd.DataFrame,
    date: pd.Timestamp,
    universe: list[str],
    lookback_months: int = 12,
    skip_months: int = 0,
    use_tbill: bool = True,
    k: int = 3,
) -> dict[str, float]:
    spec = StrategySpec("RAM", "ram", lookback_months, skip_months, use_tbill, k)
    return signal_weights(data, date, universe, spec)
