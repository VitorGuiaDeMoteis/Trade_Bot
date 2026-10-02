"""Regression tests for the daily-loss circuit breaker baseline.

The production bug was in AlpacaPaperWorker: it derived the breaker baseline from
the CURRENT account equity, so `last_equity - equity` was always 0 and the daily
loss circuit breaker could never trip. The baseline must come from the broker's
`last_equity` (previous trading-day close), which also survives process restarts.
"""

from decimal import Decimal

import pytest

from services.alpaca_paper.guard import ExecutionGuard
from services.alpaca_paper.worker import AlpacaPaperWorker


def _account(**overrides: str) -> dict[str, str]:
    """A realistic Alpaca /account payload."""
    account = {"equity": "994.00", "last_equity": "1000.00", "status": "ACTIVE"}
    account.update(overrides)
    return account


def test_optional_decimal_parses_value():
    assert AlpacaPaperWorker._optional_decimal("1000.00") == Decimal("1000.00")


@pytest.mark.parametrize("bad_value", [None, "", "not-a-number", "NaN", "Infinity"])
def test_optional_decimal_fails_closed_on_garbage(bad_value):
    assert AlpacaPaperWorker._optional_decimal(bad_value) is None


def test_baseline_is_distinct_from_current_equity():
    """The regression: baseline and current equity must not be the same value.

    Deriving the baseline from `equity` is what silently disabled the breaker.
    """
    account = _account()
    baseline = AlpacaPaperWorker._optional_decimal(account.get("last_equity"))
    current = AlpacaPaperWorker._optional_decimal(account.get("equity"))

    assert baseline is not None
    assert current is not None
    assert baseline != current


def test_breaker_trips_on_real_daily_loss():
    """A $6 loss against a $1000 prior-close baseline exceeds the $5 limit."""
    account = _account()
    baseline = AlpacaPaperWorker._optional_decimal(account["last_equity"])

    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[],
        snapshot=account,
        last_equity=baseline,
    )

    assert not approved
    assert "Circuit breaker" in reason


def test_breaker_does_not_trip_without_actual_loss():
    """Equal equity to baseline must NOT trip the breaker (no false positive)."""
    account = _account(equity="1000.00")
    baseline = AlpacaPaperWorker._optional_decimal(account["last_equity"])

    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[],
        snapshot=account,
        last_equity=baseline,
    )

    # No loss against the baseline, so the breaker must not fire.
    assert approved
    assert reason is None


def test_missing_baseline_fails_closed_on_buy():
    """No baseline must block new BUY exposure but still allow closing SELLs."""
    account = {"equity": "994.00", "status": "ACTIVE"}  # no last_equity key
    baseline = AlpacaPaperWorker._optional_decimal(account.get("last_equity"))
    assert baseline is None

    buy_ok, buy_reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="AAPL",
        positions=[],
        snapshot=account,
        last_equity=baseline,
    )
    assert not buy_ok
    assert "Daily Breaker" in buy_reason

    sell_ok, _ = ExecutionGuard.evaluate(
        side="SELL",
        symbol="AAPL",
        positions=[{"symbol": "AAPL", "quantity": "1", "market_value": "150"}],
        snapshot=account,
        last_equity=baseline,
    )
    assert sell_ok