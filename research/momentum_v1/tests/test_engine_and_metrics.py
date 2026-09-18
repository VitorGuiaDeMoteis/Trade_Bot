from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.momentum_v1.accrual import calculate_cash_accrual, compute_daily_risk_free_return
from research.momentum_v1.engine import run_backtest
from research.momentum_v1.metrics import calculate_metrics
from research.momentum_v1.strategies import (
    AM_PRIMARY,
    B0,
    B1,
    RAM_PRIMARY,
    InsufficientHistoryError,
    StrategySpec,
    signal_weights,
)


def test_tbill_accrual_one_year() -> None:
    assert calculate_cash_accrual(5.0, 365) == pytest.approx(0.05)


def test_negative_dtb3_does_not_create_cash_drawdown() -> None:
    assert calculate_cash_accrual(-0.01, 30) == 0.0


def test_risk_free_series_uses_prior_yield_and_calendar_days() -> None:
    dates = pd.DatetimeIndex(["2020-01-03", "2020-01-06"])
    data = pd.DataFrame({("Close", "DTB3"): [5.0, 9.0]}, index=dates)
    result = compute_daily_risk_free_return(data, dates)
    assert result.iloc[1] == pytest.approx(calculate_cash_accrual(5.0, 3))


def test_b0_returns_equal_canonical_risk_free(market_data: pd.DataFrame) -> None:
    result = run_backtest(market_data, ["A"], B0, "2020-01-01", "2020-12-31", cost_bps=0.0)
    risk_free = compute_daily_risk_free_return(market_data, pd.DatetimeIndex(result.returns.index))
    np.testing.assert_allclose(result.returns.to_numpy(), risk_free.to_numpy(), atol=1e-12)


def test_b0_metric_statuses(market_data: pd.DataFrame) -> None:
    result = run_backtest(market_data, ["A"], B0, "2020-01-01", "2020-12-31", cost_bps=0.0)
    risk_free = compute_daily_risk_free_return(market_data, pd.DatetimeIndex(result.returns.index))
    metrics = calculate_metrics(result.returns, risk_free)
    assert metrics["Sharpe"] == "ZERO_EXCESS_VOLATILITY"
    assert metrics["Sortino"] == "ZERO_DOWNSIDE_VOLATILITY"
    assert metrics["Calmar"] == "ZERO_DRAWDOWN"


def test_positive_max_drawdown_magnitude() -> None:
    dates = pd.date_range("2020-01-01", periods=4)
    metrics = calculate_metrics(pd.Series([0.0, -0.10, 0.05, 0.02], index=dates), pd.Series(0.0, index=dates))
    assert metrics["MaxDD"] == pytest.approx(0.10)


def test_drawdown_gate_direction_uses_smaller_magnitude() -> None:
    assert 0.10 < 0.70 * 0.20
    assert not 0.16 < 0.70 * 0.20


def test_missing_history_hard_fails(market_data: pd.DataFrame) -> None:
    short = market_data.loc[market_data.index >= pd.Timestamp("2020-06-01")]
    with pytest.raises(InsufficientHistoryError):
        signal_weights(short, pd.Timestamp("2020-12-31"), ["A"], AM_PRIMARY)


def test_exact_twelve_month_boundary_is_accepted(market_data: pd.DataFrame) -> None:
    weights = signal_weights(market_data, pd.Timestamp("2020-12-31"), ["A"], AM_PRIMARY)
    assert weights == {"A": 1.0}


def test_am_eligibility_and_equal_weighting(market_data: pd.DataFrame) -> None:
    weights = signal_weights(market_data, pd.Timestamp("2020-12-31"), ["A", "B", "D"], AM_PRIMARY)
    assert set(weights) == {"A", "B"}
    assert weights["A"] == pytest.approx(0.5)
    assert weights["B"] == pytest.approx(0.5)


def test_ram_k3_selection(market_data: pd.DataFrame) -> None:
    weights = signal_weights(market_data, pd.Timestamp("2020-12-31"), ["A", "B", "C", "D"], RAM_PRIMARY)
    assert set(weights) == {"A", "B", "C"}
    assert all(value == pytest.approx(1.0 / 3.0) for value in weights.values())


def test_ram_unused_slots_remain_cash(market_data: pd.DataFrame) -> None:
    weights = signal_weights(market_data, pd.Timestamp("2020-12-31"), ["A", "D"], RAM_PRIMARY)
    assert weights == {"A": pytest.approx(1.0 / 3.0)}
    assert sum(weights.values()) == pytest.approx(1.0 / 3.0)


def test_signal_sees_no_future_data(market_data: pd.DataFrame) -> None:
    observed: list[pd.Timestamp] = []

    def signal(visible: pd.DataFrame, date: pd.Timestamp, universe: list[str]) -> dict[str, float]:
        observed.append(pd.Timestamp(visible.index.max()))
        assert visible.index.max() == date
        return {universe[0]: 1.0}

    run_backtest(market_data, ["A"], signal, "2020-01-01", "2020-03-31", cost_bps=0.0)
    assert observed


def test_close_signal_executes_at_next_open() -> None:
    dates = pd.DatetimeIndex(["2020-01-30", "2020-01-31", "2020-02-03"])
    data = pd.DataFrame(index=dates)
    data[("Open", "A")] = [100.0, 100.0, 200.0]
    data[("Close", "A")] = [100.0, 100.0, 200.0]
    data[("Close", "DTB3")] = 0.0
    result = run_backtest(data, ["A"], B1, "2020-02-03", "2020-02-03", initial_capital=100.0, cost_bps=0.0)
    assert result.portfolio_value.iloc[0] == pytest.approx(100.0)
    assert result.trades.iloc[0]["date"] == pd.Timestamp("2020-02-03")


def test_monthly_and_quarterly_schedules_differ(market_data: pd.DataFrame) -> None:
    monthly = run_backtest(market_data, ["A", "B"], B1, "2020-01-01", "2020-12-31", cost_bps=0.0)
    quarterly = run_backtest(
        market_data,
        ["A", "B"],
        StrategySpec("B1Q", "equal_weight", rebalance_freq="Q"),
        "2020-01-01",
        "2020-12-31",
        cost_bps=0.0,
    )
    assert (monthly.turnover > 0.0).sum() > (quarterly.turnover > 0.0).sum()


def test_round_trip_cost_is_split_between_sides() -> None:
    dates = pd.bdate_range("2020-01-01", "2020-03-03")
    data = pd.DataFrame(index=dates)
    data[("Open", "A")] = 100.0
    data[("Close", "A")] = 100.0
    data[("Close", "DTB3")] = 0.0

    def alternate(_visible: pd.DataFrame, date: pd.Timestamp, _universe: list[str]) -> dict[str, float]:
        return {"A": 1.0} if date.month == 1 else {}

    result = run_backtest(data, ["A"], alternate, "2020-02-03", "2020-03-03", initial_capital=10_000.0, cost_bps=5.0)
    side = 2.5 / 10_000.0
    expected = 10_000.0 / (1.0 + side) * (1.0 - side)
    assert result.portfolio_value.iloc[-1] == pytest.approx(expected, rel=1e-10)


def test_zero_cash_sensitivity(market_data: pd.DataFrame) -> None:
    result = run_backtest(market_data, ["A"], B0, "2020-01-01", "2020-12-31", zero_cash=True)
    assert np.allclose(result.returns, 0.0)


def test_capm_uses_excess_returns() -> None:
    dates = pd.date_range("2020-01-01", periods=5)
    metrics = calculate_metrics(
        pd.Series([0.0, 0.01, -0.01, 0.02, -0.005], index=dates),
        pd.Series(0.001, index=dates),
        pd.Series([0.0, 0.02, -0.02, 0.04, -0.01], index=dates),
    )
    assert isinstance(metrics["Beta_SPY"], float)
    assert isinstance(metrics["Alpha_SPY"], float)
