"""Canonical FRED DTB3 cash accrual used by both B0 and risk metrics."""

from __future__ import annotations

import math

import pandas as pd


def calculate_cash_accrual(annual_yield_pct: float, days_held: int) -> float:
    if days_held < 0:
        raise ValueError("days_held must be non-negative")
    if math.isnan(annual_yield_pct):
        raise ValueError("Missing DTB3 yield cannot silently become zero cash return")
    effective_yield = max(annual_yield_pct, 0.0)
    return float((1.0 + effective_yield / 100.0) ** (days_held / 365.0) - 1.0)


def extract_dtb3(data: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(data, pd.Series):
        series = data.astype(float)
    elif ("Close", "DTB3") in data.columns:
        series = data[("Close", "DTB3")].astype(float)
    elif "DTB3" in data.columns:
        series = data["DTB3"].astype(float)
    else:
        raise KeyError("Canonical DTB3 series is missing")
    series.index = pd.DatetimeIndex(series.index).tz_localize(None)
    return series.sort_index().ffill()


def compute_daily_risk_free_return(
    data: pd.DataFrame | pd.Series,
    target_index: pd.DatetimeIndex,
    *,
    zero_cash: bool = False,
) -> pd.Series:
    """Return cash accrual from the preceding target session to each target session."""
    index = pd.DatetimeIndex(target_index).tz_localize(None).sort_values()
    if index.has_duplicates:
        raise ValueError("Target sessions must be unique")
    if zero_cash:
        return pd.Series(0.0, index=index, name="risk_free_return")

    yields = extract_dtb3(data)
    values = [0.0]
    for previous, current in zip(index[:-1], index[1:], strict=True):
        available = yields.loc[:previous]
        if available.empty or pd.isna(available.iloc[-1]):
            raise ValueError(f"Missing DTB3 history at {previous.date()}")
        values.append(
            calculate_cash_accrual(float(available.iloc[-1]), int((current - previous).days))
        )
    return pd.Series(values, index=index, name="risk_free_return", dtype=float)


def compound_period_return(returns: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    selected = returns.loc[(returns.index > start) & (returns.index <= end)]
    if selected.empty and end > start:
        raise ValueError("No canonical cash returns exist in the requested period")
    values = selected.to_numpy(dtype=float)
    return float((1.0 + values).prod() - 1.0)
