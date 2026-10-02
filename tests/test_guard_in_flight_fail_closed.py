"""Guard must fail CLOSED on unsourceable in-flight/position quantities.

Same bug class already recorded in AGENT_LESSONS.md ("constant-delta comparison
from one snapshot" / silent `dict.get(key, 0)` fail-open), one layer further
down: the guard's exposure and in-flight accounting substituted INVENTED zeros
for broker fields it could not read.

Concrete bypasses this closes:

- a pending SELL with a missing `quantity` counted as 0 sold, so
  `available_qty = current_qty - 0` and a second SELL of the whole position was
  approved -> oversell into a short position;
- a pending BUY with a missing/unparsable `requested_notional` contributed 0
  to in-flight exposure;
- an open position with a missing `market_value` contributed 0 to total
  exposure, so MAX_TOTAL_EXPOSURE was under-counted.

Pure guard unit tests: no Postgres, no broker, no DB mutation.
"""

from decimal import Decimal

from services.alpaca_paper.guard import ExecutionGuard

ACCOUNT = {"status": "ACTIVE", "equity": "1000", "last_equity": "1000"}


def _evaluate(side, symbol="AAPL", positions=None, in_flight=None, last_equity=Decimal("1000")):
    return ExecutionGuard.evaluate(
        side=side,
        symbol=symbol,
        positions=positions if positions is not None else [],
        snapshot=ACCOUNT,
        last_equity=last_equity,
        in_flight=in_flight if in_flight is not None else [],
        blocked_symbols=[],
        state_known=True,
    )


def test_pending_sell_with_missing_quantity_cannot_oversell():
    """REGRESSION: a pending SELL of unknown size must not be counted as 0.

    Before the fix this returned (True, None) and the executor would submit a
    second SELL for the FULL position on top of the pending one.
    """
    positions = [{"symbol": "AAPL", "qty": "1", "market_value": "5.00"}]
    in_flight = [{"symbol": "AAPL", "side": "SELL"}]  # no "quantity" key at all

    approved, reason = _evaluate("SELL", positions=positions, in_flight=in_flight)

    assert approved is False
    assert "in-flight desconhecida" in (reason or "")


def test_pending_sell_with_unparsable_quantity_cannot_oversell():
    positions = [{"symbol": "AAPL", "qty": "1", "market_value": "5.00"}]
    in_flight = [{"symbol": "AAPL", "side": "SELL", "quantity": "not-a-number"}]

    approved, reason = _evaluate("SELL", positions=positions, in_flight=in_flight)

    assert approved is False
    assert "in-flight desconhecida" in (reason or "")


def test_pending_sell_quantity_still_enforced_when_known():
    """The known-quantity path must keep working (no over-blocking)."""
    positions = [{"symbol": "AAPL", "qty": "0.03", "market_value": "5.00"}]

    approved, _ = _evaluate(
        "SELL",
        positions=positions,
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": "0.02"}],
    )
    assert approved is True

    approved, reason = _evaluate(
        "SELL",
        positions=positions,
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": "0.03"}],
    )
    assert approved is False
    assert "SHORT" in (reason or "")


def test_buy_with_in_flight_notional_unknown_is_rejected():
    """REGRESSION: unknown in-flight BUY notional must not count as $0."""
    in_flight = [{"symbol": "SPY", "side": "BUY", "quantity": "0"}]  # no notional

    approved, reason = _evaluate("BUY", symbol="AAPL", in_flight=in_flight)

    assert approved is False
    assert "Exposição de BUY in-flight desconhecida" in (reason or "")


def test_buy_rejected_when_open_position_market_value_unknown():
    """REGRESSION: an open position with unknown market_value counted as $0,
    under-counting total exposure and letting the cap be bypassed."""
    positions = [{"symbol": "SPY", "qty": "1"}]  # market_value absent
    symbol = "AAPL"

    approved, reason = _evaluate("BUY", symbol=symbol, positions=positions)

    # Without the fix, SPY contributed 0 exposure and this BUY was approved.
    assert approved is False
    assert "indisponível" in (reason or "")


def test_buy_rejected_when_position_quantity_unknown():
    """A position dict whose qty cannot be read must not be treated as flat."""
    positions = [{"symbol": "AAPL", "market_value": "5.00"}]  # qty absent

    approved, reason = _evaluate("BUY", positions=positions)

    assert approved is False
    assert "Quantidade da posição" in (reason or "")


def test_sell_still_allowed_without_market_value():
    """Closing risk must not be blocked by an absent market_value."""
    positions = [{"symbol": "AAPL", "qty": "1"}]

    approved, reason = _evaluate("SELL", positions=positions)

    assert approved is True, reason


def test_sell_rejected_when_position_quantity_unknown():
    """A SELL needs the position size; without it, a short could be opened."""
    positions = [{"symbol": "AAPL", "market_value": "5.00"}]

    approved, reason = _evaluate("SELL", positions=positions)

    assert approved is False
    assert "Quantidade da posição" in (reason or "")


def test_exposure_cap_still_enforced_with_known_values():
    positions = [
        {"symbol": "AAPL", "qty": "1", "market_value": "10"},
        {"symbol": "SPY", "qty": "1", "market_value": "20"},
    ]

    approved, reason = _evaluate("BUY", symbol="TSLA", positions=positions)

    assert approved is False
    assert "Exposição máxima total" in (reason or "")


def test_buy_rejected_when_other_position_quantity_unknown():
    """REGRESSION: a position with unreadable qty was SKIPPED by the `qty > 0`
    filter, so its exposure was excluded from the cap entirely."""
    positions = [
        {"symbol": "SPY", "market_value": "900"},  # qty absent
        {"symbol": "AAPL", "qty": "1", "market_value": "10"},
    ]

    approved, reason = _evaluate("BUY", symbol="TSLA", positions=positions)

    assert approved is False
    assert "cálculo de exposição" in (reason or "")
