"""Guard must AGGREGATE broker position rows per symbol, not take the last one.

Same bug class already recorded in AGENT_LESSONS.md ("constant-delta comparison
from one snapshot" / silent `dict.get(key, 0)` fail-open), one layer further
down: the guard collapsed the broker's per-symbol rows with a LAST-ROW-WINS
`{p["symbol"]: p}` map, while `PaperAlpacaWorker` NETS every row it receives for
a symbol before sizing a SELL.

Two components therefore held two different numbers for the SAME position, and
the guard's answer depended on the ORDER the broker happened to list rows in:

- rows `[+0.03, -0.02]` -> guard saw -0.02 -> SELL rejected as an illegal
  SHORT, stranding a genuinely long 0.01 position that the worker would have
  happily closed;
- rows `[-0.02, +0.03]` -> guard saw +0.03 -> SELL approved on a magnitude the
  netted position (0.01) never justified.

Exposure had the mirror-image defect: the cap summed every row's `market_value`
GROSS, so a hedged pair counted 150 of exposure when the net position was 15.

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


def _long(qty, market_value, symbol="AAPL"):
    return {"symbol": symbol, "qty": qty, "market_value": market_value}


def test_sell_decision_does_not_depend_on_broker_row_order():
    """REGRESSION: the same rows in a different ORDER must give the same verdict.

    Before the fix the last-row-wins map returned (False, SHORT) for one order
    and (True, None) for the other, purely from listing order.
    """
    short_first = [_long("-0.02", "-6.0"), _long("0.03", "9.0")]
    long_first = [_long("0.03", "9.0"), _long("-0.02", "-6.0")]

    assert _evaluate(side="SELL", positions=short_first) == _evaluate(
        side="SELL", positions=long_first
    )


def test_netted_position_can_still_be_closed():
    """A hedged position that nets to a real long must be sellable.

    Net qty is 0.5, so the position exists and the SELL is a position-closing
    trade, not a short.
    """
    approved, reason = _evaluate(side="SELL", positions=[_long("5", "150"), _long("-4.5", "-135")])
    assert approved, reason


def test_position_netting_to_zero_reports_no_position_to_sell():
    """Rows that net to exactly 0 leave nothing to sell: still fail closed.

    Pinning this stops a future change from reading the NET as available qty.
    """
    approved, reason = _evaluate(side="SELL", positions=[_long("5", "150"), _long("-5", "-150")])
    assert not approved
    assert reason is not None and "SHORT" in reason


def test_unsourceable_row_fails_closed_instead_of_netting_the_others():
    """A row whose qty cannot be sourced makes the NET unknown, not zero.

    Inventing the missing leg as 0 would state a position the broker never
    reported, so the SELL must be refused rather than sized from partial data.
    """
    approved, reason = _evaluate(
        side="SELL", positions=[{"symbol": "AAPL", "market_value": "2"}, _long("5", "2")]
    )
    assert not approved
    assert reason is not None and "indispon" in reason


def test_exposure_cap_uses_netted_market_value_per_symbol():
    """REGRESSION: hedged rows must not each contribute gross market value.

    AAPL nets to 15 of exposure. Counted gross (150) the cap trip: 150 + 10 >
    30. Netted, 15 + 10 = 25 fits, so the BUY is legitimately approvable and
    was rejected for the wrong reason.
    """
    hedged = [_long("5", "150", "AAPL"), _long("-4.5", "-135", "AAPL")]
    approved, reason = _evaluate(side="BUY", symbol="TSLA", positions=hedged)
    assert approved, reason


def test_gross_exposure_still_trips_the_cap_for_real_holds():
    """Netting must not weaken the cap: two genuinely long symbols still trip it.

    TSLA 20 + SPY 12 nets to 32 of exposure, so 32 + 10 > 30 rejects.
    """
    positions = [_long("1", "20", "TSLA"), _long("1", "12", "SPY")]
    approved, reason = _evaluate(side="BUY", symbol="AAPL", positions=positions)
    assert not approved
    assert reason is not None and "Exposição" in reason
