"""The daily-loss breaker must say WHICH side of the equity delta was missing.

The breaker has two independent fail-closed paths:

- the baseline (``last_equity``, the broker's previous trading-day close) is
  absent, zero or unparsable;
- the current ``equity`` in the account snapshot is absent or unparsable.

Both used to return the identical string "Equity indisponível para checagem do
Daily Breaker", so an operator reading only the rejection reason could not tell
an account payload with no ``last_equity`` apart from one with no ``equity``.
The two have different remediations, so the reason must name the side.

These are pure guard unit tests: no Postgres, no broker, no DB mutation.

Invariant under test: BOTH reasons keep the shared "Equity indisponível" prefix,
so existing log greps and assertions that match the old message keep working.
"""

from decimal import Decimal

from services.alpaca_paper.guard import ExecutionGuard

BASE_ACCOUNT = {"status": "ACTIVE", "currency": "USD"}


def _buy_reason(snapshot, last_equity):
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="SPY",
        positions=[],
        snapshot=snapshot,
        last_equity=last_equity,
        in_flight=[],
        blocked_symbols=[],
        state_known=True,
    )
    assert approved is False, "equity-unavailable cases must fail closed"
    assert reason is not None
    return reason


def test_missing_baseline_names_the_baseline_side():
    reason = _buy_reason({**BASE_ACCOUNT, "equity": "100.00"}, None)
    assert "Equity indisponível" in reason
    assert "baseline last_equity" in reason


def test_zero_baseline_names_the_baseline_side():
    """A 0 baseline is unavailable, not a valid baseline, and must say so."""
    reason = _buy_reason({**BASE_ACCOUNT, "equity": "100.00"}, Decimal("0"))
    assert "baseline last_equity" in reason


def test_missing_current_equity_names_the_current_side():
    reason = _buy_reason({**BASE_ACCOUNT}, Decimal("100.00"))
    assert "Equity indisponível" in reason
    assert "equity atual ausente ou inválido" in reason
    assert "baseline last_equity ausente" not in reason


def test_unparsable_current_equity_names_the_current_side():
    reason = _buy_reason({**BASE_ACCOUNT, "equity": "N/A"}, Decimal("100.00"))
    assert "equity atual ausente ou inválido" in reason


def test_missing_snapshot_names_the_current_side():
    """No snapshot at all means no current equity, but the baseline may be fine."""
    reason = _buy_reason(None, Decimal("100.00"))
    assert "equity atual ausente ou inválido" in reason


def test_both_sides_unavailable_reports_the_baseline_first():
    """With nothing available, naming the baseline keeps the two reasons stable."""
    reason = _buy_reason(None, None)
    assert "baseline last_equity ausente" in reason


def test_healthy_account_never_sees_either_message():
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="SPY",
        positions=[],
        snapshot={**BASE_ACCOUNT, "equity": "100.50"},
        last_equity=Decimal("100.00"),
    )
    assert approved is True, reason
    assert reason is None


def test_real_daily_loss_message_is_unchanged():
    """A genuine breaker trip must not be confused with missing data."""
    approved, reason = ExecutionGuard.evaluate(
        side="BUY",
        symbol="SPY",
        positions=[],
        snapshot={**BASE_ACCOUNT, "equity": "94.00"},
        last_equity=Decimal("100.00"),
    )
    assert approved is False
    assert reason is not None
    assert "Circuit breaker diário" in reason
    assert "Equity indisponível" not in reason


def test_sell_to_close_ignores_the_equity_observability_split():
    """Closing risk must stay available while equity data is degraded."""
    approved, reason = ExecutionGuard.evaluate(
        side="SELL",
        symbol="SPY",
        positions=[{"symbol": "SPY", "qty": "1", "market_value": "50.00"}],
        snapshot={**BASE_ACCOUNT},
        last_equity=None,
    )
    assert approved is True, reason
    assert reason is None
