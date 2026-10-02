"""Daily-loss breaker must fail CLOSED when current equity is unavailable.

Bug class documented in AGENT_LESSONS.md: a safety comparison whose two sides
must be independently sourced. The guard computed
``equity = Decimal(str(snapshot.get("equity", 0)))``, so a broker account
payload missing ``equity`` silently substituted an invented 0. The delta
``last_equity - equity`` then compared a REAL baseline against a FABRICATED
value, and whenever ``last_equity`` was below DAILY_LOSS_LIMIT the delta stayed
under the limit and the breaker was BYPASSED -- worst case a nearly-wiped
account passed the daily-loss check on no information at all.

These are pure guard unit tests: no Postgres, no broker, no DB mutation.
"""

from decimal import Decimal

from services.alpaca_paper.guard import ExecutionGuard

BASE_ACCOUNT = {"status": "ACTIVE", "currency": "USD"}


def _evaluate(side, snapshot, last_equity, positions=None):
    return ExecutionGuard.evaluate(
        side=side,
        symbol="SPY",
        positions=positions if positions is not None else [],
        snapshot=snapshot,
        last_equity=last_equity,
        in_flight=[],
        blocked_symbols=[],
        state_known=True,
    )


def test_missing_equity_below_limit_baseline_is_rejected():
    """REGRESSION: baseline below the loss limit must NOT let a missing
    equity through. Before the fix this returned (True, None)."""
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "last_equity": "3.00"},  # no "equity" key at all
        Decimal("3.00"),
    )
    assert approved is False
    assert "Equity indisponível" in reason


def test_unparsable_equity_is_rejected():
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "equity": "N/A", "last_equity": "100.00"},
        Decimal("100.00"),
    )
    assert approved is False
    assert "Equity indisponível" in reason


def test_healthy_account_is_approved():
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "equity": "100.50", "last_equity": "100.00"},
        Decimal("100.00"),
    )
    assert approved is True, reason


def test_real_daily_loss_still_trips_breaker():
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "equity": "94.00", "last_equity": "100.00"},
        Decimal("100.00"),
    )
    assert approved is False
    assert "Circuit breaker diário" in reason


def test_absent_baseline_still_fails_closed():
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "equity": "100.00"},
        None,
    )
    assert approved is False
    assert "Equity indisponível" in reason


def test_zero_baseline_fails_closed():
    approved, reason = _evaluate(
        "BUY",
        {**BASE_ACCOUNT, "equity": "100.00", "last_equity": "0"},
        Decimal("0"),
    )
    assert approved is False
    assert "Equity indisponível" in reason


def test_missing_snapshot_fails_closed():
    approved, reason = _evaluate("BUY", None, Decimal("100.00"))
    assert approved is False
    assert "Equity indisponível" in reason


def test_sell_to_close_is_not_blocked_by_missing_equity():
    """Fail-closed must apply to opening risk only; closing SELLs still work."""
    positions = [{"symbol": "SPY", "qty": "1", "market_value": "50.00"}]
    approved, reason = _evaluate(
        "SELL",
        {**BASE_ACCOUNT, "last_equity": "3.00"},
        Decimal("3.00"),
        positions=positions,
    )
    assert approved is True, reason
