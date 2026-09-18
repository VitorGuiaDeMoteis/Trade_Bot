"""Fractional-share execution replay; never connects to a broker."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MicroReplayResult:
    records: pd.DataFrame
    quantities: pd.DataFrame
    position_dollars: pd.DataFrame


def _numeric(value: object, *, label: str) -> float:
    if not isinstance(value, Real):
        raise TypeError(f"{label} must be numeric")
    return float(value)


def run_micro_replay(
    data: pd.DataFrame,
    universe: list[str],
    target_weights: pd.DataFrame,
    initial_capital: float = 50.0,
    min_notional: float = 1.0,
    frac_precision: int = 6,
    cost_bps_roundtrip: float = 5.0,
) -> MicroReplayResult:
    cash = float(initial_capital)
    shares = {symbol: 0.0 for symbol in universe}
    side_rate = cost_bps_roundtrip / 2.0 / 10_000.0
    records: list[dict[str, float]] = []
    quantity_rows: list[dict[str, float]] = []
    dollar_rows: list[dict[str, float]] = []
    dates: list[pd.Timestamp] = []

    for raw_date, row in target_weights.iterrows():
        date = cast(pd.Timestamp, raw_date)
        if date not in data.index:
            raise ValueError(f"Target date {date.date()} is not a market session")
        weights = {symbol: _numeric(row.get(symbol, 0.0), label=f"{symbol} weight") for symbol in universe}
        if any(np.isnan(value) for value in weights.values()):
            continue
        open_prices = {symbol: _numeric(data.at[date, ("Open", symbol)], label=f"{symbol} open") for symbol in universe}
        nav = cash + sum(shares[symbol] * open_prices[symbol] for symbol in universe)
        tradable_nav = nav / (1.0 + side_rate)
        turnover = 0.0
        rounding_residual = 0.0
        below_minimum = 0
        for symbol in universe:
            target_dollars = tradable_nav * weights[symbol]
            current_dollars = shares[symbol] * open_prices[symbol]
            delta_dollars = target_dollars - current_dollars
            if 0.0 < abs(delta_dollars) < min_notional and not (target_dollars == 0.0 and shares[symbol] != 0.0):
                below_minimum += 1
                continue
            exact_delta = delta_dollars / open_prices[symbol]
            rounded_delta = round(exact_delta, frac_precision)
            executed = rounded_delta * open_prices[symbol]
            rounding_residual += delta_dollars - executed
            turnover += abs(executed)
            shares[symbol] += rounded_delta
            cash -= executed + abs(executed) * side_rate

        dollars = {symbol: shares[symbol] * open_prices[symbol] for symbol in universe}
        ending_nav = cash + sum(dollars.values())
        effective_weights = np.array([dollars[symbol] / ending_nav for symbol in universe], dtype=float)
        desired_weights = np.array([weights[symbol] for symbol in universe], dtype=float)
        records.append(
            {
                "nav": ending_nav,
                "cash_residual": cash,
                "orders_below_minimum": float(below_minimum),
                "rounding_residual": rounding_residual,
                "effective_positions": float(sum(value >= min_notional for value in dollars.values())),
                "turnover_dollars": turnover,
                "turnover_pct": turnover / nav if nav else 0.0,
                "friction_pct_nav": turnover * side_rate / nav if nav else 0.0,
                "tracking_error": float(np.sqrt(np.sum((effective_weights - desired_weights) ** 2))),
            }
        )
        quantity_rows.append(shares.copy())
        dollar_rows.append(dollars)
        dates.append(date)
    return MicroReplayResult(
        records=pd.DataFrame(records, index=dates),
        quantities=pd.DataFrame(quantity_rows, index=dates),
        position_dollars=pd.DataFrame(dollar_rows, index=dates),
    )
