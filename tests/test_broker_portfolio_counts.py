"""Regression: the ALPACA_PAPER portfolio must report real order/fill totals.

`get_broker_portfolio` used to omit `orders_count`/`fills_count` when building
the `PaperPortfolio`, so the contract defaults reported 0 while the very same
payload carried populated `orders`/`fills` lists.  These tests pin the totals
without touching Postgres: the route is called directly against a stub
connection that dispatches on the statement being executed.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import Response

from services.api.broker_routes import get_broker_portfolio

NOW = datetime.now(UTC)


def _order_row() -> dict[str, Any]:
    return {
        "order_id": uuid4(),
        "run_id": uuid4(),
        "signal_id": uuid4(),
        "risk_decision_id": uuid4(),
        "symbol": "SPY",
        "side": "BUY",
        "requested_quantity": Decimal("1"),
        "filled_quantity": Decimal("1"),
        "status": "filled",
        "last_reconciled_at": NOW,
        "client_order_id": f"cid-{uuid4()}",
        "broker_order_id": f"boid-{uuid4()}",
    }


def _fill_row(order_id: Any) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-{uuid4()}",
        "order_id": order_id,
        "price": Decimal("612.5"),
        "quantity": Decimal("1"),
        "fee": None,
        "filled_at": NOW,
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
    ) -> None:
        self._control = control
        self._positions = positions
        self._orders = orders
        self._fills = fills
        self._order_total = order_total
        self._fill_total = fill_total
        self.statements: list[str] = []

    def execute(self, statement: Any) -> "_Result":
        text = str(statement)
        self.statements.append(text)
        if "system_controls" in text:
            return _Result([self._control] if self._control else [])
        if "broker_portfolio_snapshots" in text:
            return _Result([dict(_SNAPSHOT)])
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
