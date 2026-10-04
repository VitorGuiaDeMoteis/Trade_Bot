"""Regression: the ALPACA_PAPER portfolio must report real order/fill totals.

`get_broker_portfolio` used to omit `orders_count`/`fills_count` when building
the `PaperPortfolio`, so the contract defaults reported 0 while the very same
payload carried populated `orders`/`fills` lists.  These tests pin the totals
without touching Postgres: the route is called directly against a stub
connection that dispatches on the statement being executed.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import Response

from services.api.broker_routes import get_broker_portfolio

NOW = datetime.now(UTC)
SUBMITTED_AT = NOW - timedelta(hours=2)


def _order_row(
    *,
    requested_at: datetime | None = None,
    requested_quantity: Decimal | str | None = Decimal("1"),
    filled_quantity: Decimal | str = Decimal("1"),
    status: str = "filled",
    paper_status: str = "FILLED",
) -> dict[str, Any]:
    """One joined broker_orders+paper_orders row.

    `requested_at` is paper_orders' immutable submit time; `last_reconciled_at`
    is broker_orders' timestamp, bumped on EVERY reconcile cycle. They are kept
    deliberately distinct so a test can tell which one the route reported.

    `requested_quantity` defaults to a real share count but accepts None,
    because a NOTIONAL order (the BUY branch sends dollars, not shares) stores
    NULL there by design -- see the route's quantity mapping.

    `status` is the RAW broker text (broker_orders.status) and `paper_status` is
    the MAPPED local value (paper_orders.status, the executor's _map_status
    output, CHECK-constrained to the contract Literal). They are separate keys
    with separate defaults and are deliberately NOT derived from one another, so
    a test can prove which of the two the route reports. The route selects the
    local column under the label `paper_status` to avoid colliding with the
    broker column the full `select(broker_orders, ...)` expansion also brings in.
    """
    return {
        "order_id": uuid4(),
        "run_id": uuid4(),
        "signal_id": uuid4(),
        "risk_decision_id": uuid4(),
        "symbol": "SPY",
        "side": "BUY",
        "requested_quantity": requested_quantity,
        "filled_quantity": filled_quantity,
        "status": status,
        "paper_status": paper_status,
        "requested_at": SUBMITTED_AT if requested_at is None else requested_at,
        "last_reconciled_at": NOW,
        "client_order_id": f"cid-{uuid4()}",
        "broker_order_id": f"boid-{uuid4()}",
    }


def _fill_row(order_id: Any, *, filled_at: datetime | None = None) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-{uuid4()}",
        "order_id": order_id,
        "price": Decimal("612.5"),
        "quantity": Decimal("1"),
        "fee": None,
        "filled_at": SUBMITTED_AT + timedelta(minutes=5) if filled_at is None else filled_at,
    }


def _position_row() -> dict[str, Any]:
    return {
        "symbol": "SPY",
        "quantity": Decimal("0.012974261"),
        "average_price": Decimal("612.5"),
        "current_price": Decimal("612.5"),
        "market_value": Decimal("7.94"),
        "unrealized_pnl": Decimal("0"),
        "updated_at": NOW,
    }


_SNAPSHOT = {
    "provider": "alpaca",
    "status": "ACTIVE",
    "cash": Decimal("99941.36"),
    "market_value": Decimal("9.98"),
    "equity": Decimal("99951.34"),
    "unrealized_pnl": Decimal("-0.00877"),
    "buying_power": Decimal("99941.36"),
    "last_reconciled_at": NOW,
}


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Result:
    """Mimics the `Result.mappings()` chain the route uses."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class _StubConnection:
    """Serves canned rows by inspecting which table each statement targets."""

    def __init__(
        self,
        *,
        control: dict[str, Any] | None,
        positions: list[dict[str, Any]],
        orders: list[dict[str, Any]],
        fills: list[dict[str, Any]],
        order_total: int,
        fill_total: int,
        snapshot_status: str = "ACTIVE",
    ) -> None:
        self._control = control
        self._positions = positions
        self._orders = orders
        self._fills = fills
        self._order_total = order_total
        self._fill_total = fill_total
        # `status` is the reconciliation LATCH the worker writes (see
        # `_save_broker_snapshot` / `_enter_degraded`), not a health probe, so
        # a test can drive the portfolio's flags by setting it per case.
        self._snapshot = {**_SNAPSHOT, "status": snapshot_status}
        self.statements: list[str] = []

    def execute(self, statement: Any) -> "_Result":
        text = str(statement)
        self.statements.append(text)
        if "system_controls" in text:
            return _Result([self._control] if self._control else [])
        if "broker_portfolio_snapshots" in text:
            return _Result([dict(self._snapshot)])
        if "broker_positions" in text:
            return _Result(self._positions)
        if "broker_orders" in text:
            return _Result(self._orders)
        if "broker_fills" in text:
            return _Result(self._fills)
        raise AssertionError(f"unexpected statement: {text}")

    def scalar(self, statement: Any) -> int:
        text = str(statement)
        self.statements.append(text)
        if "broker_fills" in text:
            return self._fill_total
        if "broker_orders" in text:
            return self._order_total
        raise AssertionError(f"unexpected scalar statement: {text}")


class _StubEngine:
    def __init__(self, conn: _StubConnection) -> None:
        self._conn = conn

    def begin(self) -> "_StubEngine":
        return self

    def __enter__(self) -> _StubConnection:
        return self._conn

    def __exit__(self, *exc: object) -> bool:
        return False


def _request(conn: _StubConnection) -> Any:
    app = SimpleNamespace(
        state=SimpleNamespace(
            configuration=SimpleNamespace(execution_mode="alpaca_paper"),
            database=_StubEngine(conn),
        )
    )
    return SimpleNamespace(app=app)


def _call(conn: _StubConnection) -> Any:
    return asyncio.run(get_broker_portfolio(_request(conn), Response()))


def test_portfolio_reports_real_order_and_fill_counts() -> None:
    """Totals are reported even though the payload also carries the rows."""
    order_rows = [_order_row() for _ in range(3)]
    fill_rows = [_fill_row(order_rows[0]["order_id"]) for _ in range(2)]
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order_rows[0]["run_id"]},
        positions=[_position_row()],
        orders=order_rows,
        fills=fill_rows,
        order_total=3,
        fill_total=2,
    )

    portfolio = _call(conn)

    assert len(portfolio.orders) == 3
    assert len(portfolio.fills) == 2
    assert portfolio.orders_count == 3
    assert portfolio.fills_count == 2


def test_counts_come_from_count_query_not_capped_list_length() -> None:
    """The lists are LIMIT 100, so totals must not be len() of what was returned."""
    order_rows = [_order_row() for _ in range(2)]
    fill_rows = [_fill_row(order_rows[0]["order_id"])]
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order_rows[0]["run_id"]},
        positions=[],
        orders=order_rows,
        fills=fill_rows,
        order_total=250,
        fill_total=140,
    )

    portfolio = _call(conn)

    assert (portfolio.orders_count, portfolio.fills_count) == (250, 140)
    # Guard the regression itself: the counts must not collapse to the list length.
    assert portfolio.orders_count != len(portfolio.orders)
    assert portfolio.fills_count != len(portfolio.fills)
    assert any("count" in s for s in conn.statements)


def test_empty_broker_state_reports_zero_counts() -> None:
    """A fresh run has no rows; counts must be 0, not None or missing."""
    conn = _StubConnection(
        control={"paused": False, "active_run_id": None},
        positions=[],
        orders=[],
        fills=[],
        order_total=0,
        fill_total=0,
    )

    portfolio = _call(conn)

    assert portfolio.orders == [] and portfolio.fills == []
    assert portfolio.orders_count == 0
    assert portfolio.fills_count == 0


def test_notional_order_reports_real_share_count_not_fabricated_zero() -> None:
    """A notional order must never be published as quantity=0.

    executor.py stores requested_quantity as NULL for a notional BUY because
    the share count is unknowable until the broker fills it. The route used to
    coerce that NULL to 0, so the API advertised "quantity: 0" beside a real
    filled_quantity -- a trade that appears to have traded nothing.
    """
    order = _order_row(requested_quantity=None, filled_quantity="0.0007")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    portfolio = _call(conn)

    published = portfolio.orders[0]
    assert published.quantity == Decimal("0.0007")
    assert published.quantity != 0
    assert published.filled_quantity == Decimal("0.0007")


def test_share_order_keeps_requested_quantity() -> None:
    """A share-denominated order must still report what was requested."""
    order = _order_row(requested_quantity="0.002", filled_quantity="0.002")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    portfolio = _call(conn)

    assert portfolio.orders[0].quantity == Decimal("0.002")


def test_unfilled_notional_order_reports_zero_because_it_traded_nothing() -> None:
    """An open notional order with no fill has 0 real shares -- that zero is true."""
    order = _order_row(
        requested_quantity=None, filled_quantity="0", status="new", paper_status="NEW"
    )
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    portfolio = _call(conn)

    published = portfolio.orders[0]
    assert published.quantity == 0
    assert published.status == "NEW"


def test_order_requested_at_is_submit_time_not_reconcile_time() -> None:
    """requested_at must be paper_orders' submit time.

    broker_orders.last_reconciled_at is bumped on EVERY reconcile, so using it
    as requested_at made a fill look like it happened BEFORE the order that
    produced it (the fill carries the true submit-based time).
    """
    order = _order_row()
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[_fill_row(order["order_id"])],
        order_total=1,
        fill_total=1,
    )

    portfolio = _call(conn)

    reported = portfolio.orders[0]
    assert reported.requested_at == SUBMITTED_AT
    assert reported.requested_at != NOW
    # The reconcile timestamp is still published, in its own field.
    assert reported.last_reconciled_at == NOW
    # The invariant the old mapping broke: a fill cannot precede its own order.
    assert portfolio.fills[0].filled_at > reported.requested_at


def test_order_reports_requested_at_independent_of_reconcile_frequency() -> None:
    """Reconciling repeatedly must not move requested_at.

    An order reconciled many times still has ONE submit time; only
    last_reconciled_at advances. This is the regression that would reappear if
    someone "simplified" the route back to a single timestamp column.
    """
    first = _order_row()
    order_id = first["order_id"]
    re_reconciled = _order_row()
    re_reconciled.update(
        {
            "order_id": order_id,
            "run_id": first["run_id"],
            "signal_id": first["signal_id"],
            "risk_decision_id": first["risk_decision_id"],
            "client_order_id": first["client_order_id"],
            "last_reconciled_at": NOW + timedelta(minutes=30),
        }
    )
    conn = _StubConnection(
        control={"paused": False, "active_run_id": first["run_id"]},
        positions=[],
        orders=[first, re_reconciled],
        fills=[],
        order_total=2,
        fill_total=0,
    )

    portfolio = _call(conn)

    assert [o.requested_at for o in portfolio.orders] == [SUBMITTED_AT, SUBMITTED_AT]
    # The two rows really do differ in reconcile time, so the test has teeth.
    assert portfolio.orders[0].last_reconciled_at != portfolio.orders[1].last_reconciled_at


def _orders_order_by(conn: _StubConnection) -> str:
    """The ORDER BY of the SELECT that feeds `portfolio.orders`.

    It is the only statement joining broker_orders to paper_orders with an
    ORDER BY; the totals use COUNT instead. Split off everything before the
    clause, because the projection itself mentions `last_reconciled_at`
    (broker_orders.* expands every column).
    """
    statement = next(s for s in conn.statements if "broker_orders" in s and "ORDER BY" in s)
    return statement.split("ORDER BY", 1)[1].strip()


def test_orders_sorted_by_submit_time_not_reconcile_time() -> None:
    """The list order must agree with the requested_at the payload reports.

    Sorting by broker_orders.last_reconciled_at floats an order that keeps
    being reconciled above genuinely newer ones, so the newest row of the
    response was not the newest trade.
    """
    order = _order_row()
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    _call(conn)

    order_by = _orders_order_by(conn)
    assert order_by.startswith("paper_orders.requested_at DESC")
    assert "last_reconciled_at" not in order_by


def test_orders_window_has_a_stable_tiebreaker() -> None:
    """LIMIT 100 needs a total order, or the window itself can shuffle."""
    order = _order_row()
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    _call(conn)

    order_by = _orders_order_by(conn)
    assert "paper_orders.symbol, paper_orders.order_id" in order_by


def test_order_status_is_the_mapped_local_value_not_an_uppercased_broker_string() -> None:
    """`status` must come from paper_orders, never be re-derived from broker text.

    The route used `broker_orders.status.upper()`. That happens to be correct for
    the ten states in `AlpacaPaperExecutor._map_status`, but Alpaca emits states
    OUTSIDE that map ("done_for_day", "halted", "suspended", "stopped"), and
    `.upper()` turned them into strings absent from the `PaperOrder.status`
    Literal -- so pydantic rejected the row and ONE unfamiliar order status took
    down the ENTIRE portfolio endpoint with a 500.

    The local column is authoritative: the executor already mapped it and the DB
    CHECK-constrains it to exactly the contract Literal
    (migration 863267844740, ck_paper_orders_state_m7).
    """
    order = _order_row(status="done_for_day", paper_status="FILLED")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    portfolio = _call(conn)

    published = portfolio.orders[0]
    assert published.status == "FILLED"
    # The raw broker text is preserved verbatim, in its own field.
    assert published.broker_status == "done_for_day"
    # The test has teeth: the two sources really do disagree.
    assert published.status != published.broker_status.upper()


@pytest.mark.parametrize(
    "broker_text",
    [
        "done_for_day",
        "halted",
        "suspended",
        "stopped",
        "pending_replace",
        "calculated",
        "a_state_this_map_has_never_heard_of",
    ],
)
def test_unfamiliar_broker_status_cannot_take_down_the_whole_portfolio(broker_text: str) -> None:
    """No broker order status may 500 the endpoint, whatever Alpaca emits.

    The failure mode was total, not per-row: a single order whose status was
    absent from the contract Literal failed validation of the whole response
    model, so an operator lost the ENTIRE portfolio -- positions, counts and all
    other orders -- over one unfamiliar string. The mapped local value degrades
    to UNKNOWN instead, so the payload always renders.
    """
    # What the executor stores for anything _map_status does not know.
    order = _order_row(status=broker_text, paper_status="UNKNOWN")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[_position_row()],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    portfolio = _call(conn)

    # The endpoint's whole value is that it returns at all.
    assert len(portfolio.positions) == 1
    assert len(portfolio.orders) == 1
    assert portfolio.orders[0].status == "UNKNOWN"
    assert portfolio.orders[0].broker_status == broker_text


def test_order_status_column_is_selected_under_a_label_that_cannot_shadow_broker_status() -> None:
    """The projection must take paper_orders.status, not broker_orders.status.

    The query selects the whole `broker_orders` table, whose expansion already
    includes its own `status`. Selecting `paper_orders.c.status` unlabelled
    yields a mapping with ONE ambiguous key, so this pins the label: a regression
    that dropped it would resolve `paper_status` to the raw broker text again.
    """
    order = _order_row()
    conn = _StubConnection(
        control={"paused": False, "active_run_id": order["run_id"]},
        positions=[],
        orders=[order],
        fills=[],
        order_total=1,
        fill_total=0,
    )

    _call(conn)

    projection = next(
        s for s in conn.statements if "broker_orders" in s and "ORDER BY" in s
    ).split("ORDER BY", 1)[0]
    assert "paper_orders.status AS paper_status" in projection
    # The broker column is still projected, for the verbatim broker_status field.
    assert "broker_orders.status" in projection


def _conn_for_status(status: str) -> _StubConnection:
    return _StubConnection(
        control={"paused": False, "active_run_id": None},
        positions=[_position_row()],
        orders=[],
        fills=[],
        order_total=0,
        fill_total=0,
        snapshot_status=status,
    )


@pytest.mark.parametrize("status", ["DEGRADED", "STALE"])
def test_failed_reconciliation_is_never_published_as_reconciled(status: str) -> None:
    """`reconciled` must not default to True on a snapshot whose cycle failed.

    The route derived `degraded` from the snapshot status but never passed
    `reconciled`, which the contract defaults to True. A DEGRADED/STALE book --
    one whose last reconciliation FAILED and whose positions may not match the
    broker -- was therefore published as `"reconciled": true` beside
    `"degraded": true`. Both flags describe one fact about the same latch, so
    any consumer that trusts `reconciled` (and many will, since True is the
    contract default and therefore the common case) was told a failed book had
    been verified against the broker.
    """
    portfolio = _call(_conn_for_status(status))

    assert portfolio.status == status
    assert portfolio.degraded is True
    assert portfolio.reconciled is False


def test_reconciled_is_true_only_for_a_reconciled_snapshot() -> None:
    """The control: an ACTIVE latch must still report reconciled=True.

    Without this, "always report False" would pass the test above.
    """
    portfolio = _call(_conn_for_status("ACTIVE"))

    assert portfolio.degraded is False
    assert portfolio.reconciled is True


@pytest.mark.parametrize("status", ["ACTIVE", "DEGRADED", "STALE"])
def test_reconciled_and_degraded_can_never_disagree(status: str) -> None:
    """Both flags come from the same stored latch, so they are always opposed.

    Whichever status the worker persisted, exactly one of the two must hold.
    A future edit that recomputes either flag from a second source would break
    this invariant even if it kept both current tests passing.
    """
    portfolio = _call(_conn_for_status(status))

    assert portfolio.reconciled is not portfolio.degraded
