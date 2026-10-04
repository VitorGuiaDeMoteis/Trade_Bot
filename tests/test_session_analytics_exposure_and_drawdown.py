"""The session report must MEASURE exposure and drawdown, not echo a constant.

`max_drawdown` was the literal string "0.00" and BOTH `avg_exposure` and
`max_exposure` were the CURRENT market value, so every session reported zero
drawdown and two identical "exposure" numbers that could not differ no matter
what the run traded. This pins the reconstructed curve:

- a session that buys 1 AAPL at 100 and sells at 120 has exposure 100 before the
  fill, so its time-weighted average is strictly between 0 and the peak;
- a peak-then-loss session reports a drawdown equal to the realized loss;
- a session with no fills keeps the current book as both exposures (the
  inherited-lot case, where the book is the only evidence that exists);
- an inherited lot opened by an EARLIER run has no fill here, and must still
  count toward exposure instead of vanishing from every interval.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from services.api.analytics import get_session_analytics

STARTED_AT = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
INITIAL_CASH = Decimal("1000.00")

RUN_ROW = {
    "created_at": STARTED_AT,
    "initial_cash": INITIAL_CASH,
    "provider": "ALPACA",
}


def _at(minutes: int) -> datetime:
    return STARTED_AT + timedelta(minutes=minutes)


def _fill(side: str, qty: str, price: str, minutes: int, fee: str = "0") -> dict[str, Any]:
    return {
        "broker_fill_id": f"f-{side}-{minutes}",
        "symbol": "AAPL",
        "side": side,
        "quantity": qty,
        "price": price,
        "fee": fee,
        "filled_at": _at(minutes),
    }


def _snapshot(equity: str, cash: str = "1000.00", last_reconciled_at: datetime | None = None) -> dict[str, Any]:
    return {
        "cash": cash,
        "equity": equity,
        "last_reconciled_at": last_reconciled_at or _at(120),
    }


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]] | None) -> None:
        self._rows = rows or []

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)

    def scalar(self) -> Any:
        return self._scalar


class _StubConnection:
    """Serves one run: its fills, its position book and its snapshot."""

    def __init__(
        self,
        fills: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        snapshot: dict[str, Any] | None,
    ) -> None:
        self._fills = fills
        self._positions = positions
        self._snapshot = snapshot

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = str(statement)
        if "paper_runs" in sql:
            return _Result([RUN_ROW])
        if "MAX(last_reconciled_at)" in sql:
            end = self._snapshot["last_reconciled_at"] if self._snapshot else None
            return _Result(scalar=end)
        if "broker_positions" in sql:
            return _Result(self._positions)
        if "broker_portfolio_snapshots" in sql:
            return _Result([self._snapshot] if self._snapshot else [])
        if "broker_fills" in sql:
            return _Result(self._fills)
        if "paper_orders" in sql:
            return _Result([])
        if "risk_decisions" in sql:
            return _Result([])
        raise AssertionError(f"unexpected statement: {sql}")


def _position(qty: str, market_value: str, unrealized: str = "0") -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "quantity": qty,
        "average_price": "100",
        "current_price": "120",
        "market_value": market_value,
        "unrealized_pnl": unrealized,
        "updated_at": _at(120),
    }


def _analytics(conn: _StubConnection) -> dict[str, Any]:
    return get_session_analytics(conn, "run-1")  # type: ignore[arg-type]


def test_exposure_is_a_time_weighted_curve_not_the_final_instant():
    """Exposure 0 for the first hour, then 100: the average sits below the peak."""
    conn = _StubConnection(
        fills=[_fill("BUY", "1", "100", 60)],
        # The run still holds the lot it bought, and it is marked at its fill
        # price, so the book and the fill agree. An empty book here would make
        # the backward walk subtract a notional the book never carried.
        positions=[_position("1", "100.00")],
        snapshot=_snapshot(equity="1000.00"),
    )

    result = _analytics(conn)

    assert Decimal(result["max_exposure"]) == Decimal("100.00")
    # Half the session flat, half with the lot held.
    assert Decimal(result["avg_exposure"]) == Decimal("50.00")
    assert Decimal(result["avg_exposure"]) < Decimal(result["max_exposure"])


def test_avg_and_max_exposure_can_differ_which_the_constant_pair_could_never_do():
    """Two peaks of different sizes: the average must fall strictly between them."""
    conn = _StubConnection(
        fills=[_fill("BUY", "1", "100", 20), _fill("BUY", "1", "300", 40)],
        positions=[_position("2", "400.00")],
        snapshot=_snapshot(equity="1400.00"),
    )

    result = _analytics(conn)

    peak = Decimal(result["max_exposure"])
    average = Decimal(result["avg_exposure"])
    assert peak == Decimal("400.00")
    assert Decimal("100.00") < average < peak


def test_max_drawdown_reports_the_realized_loss_instead_of_zero():
    """Buy at 100, sell at 40: the equity curve drops by the 60 loss."""
    conn = _StubConnection(
        fills=[_fill("BUY", "1", "100", 20), _fill("SELL", "1", "40", 60)],
        positions=[_position("0", "0")],
        snapshot=_snapshot(equity="940.00"),
    )

    result = _analytics(conn)

    assert Decimal(result["pnl_realized"]) == Decimal("-60.00")
    assert Decimal(result["max_drawdown"]) == Decimal("60.00")


def test_max_drawdown_measures_peak_to_trough_not_start_to_end():
    """Win then loss: start-to-end is 50 down, but the trough is 100 below the peak."""
    conn = _StubConnection(
        fills=[
            _fill("BUY", "1", "100", 20),
            _fill("SELL", "1", "150", 40),
            _fill("BUY", "1", "150", 60),
            _fill("SELL", "1", "50", 80),
        ],
        positions=[_position("0", "0")],
        snapshot=_snapshot(equity="1000.00"),
    )

    result = _analytics(conn)

    # Equity runs 1000 -> 1050 -> 950. Start-to-end is only 50 down, so a
    # start-to-end measure would call the 50 peak-to-trough loss "no drawdown".
    assert Decimal(result["pnl_realized"]) == Decimal("-50.00")
    assert Decimal(result["max_drawdown"]) == Decimal("100.00")


def test_inherited_lot_with_no_fill_here_still_counts_as_exposure():
    """The book is the only evidence for a lot opened by a previous run."""
    conn = _StubConnection(
        fills=[],
        positions=[_position("2", "240.00")],
        snapshot=_snapshot(equity="1240.00"),
    )

    result = _analytics(conn)

    assert Decimal(result["avg_exposure"]) == Decimal("240.00")
    assert Decimal(result["max_exposure"]) == Decimal("240.00")
    assert Decimal(result["max_drawdown"]) == Decimal("0.00")


def test_sell_above_the_book_keeps_exposure_non_negative():
    """Walking BACKWARD through a SELL adds its notional back, never below zero."""
    conn = _StubConnection(
        fills=[_fill("SELL", "1", "120", 60)],
        positions=[_position("0", "0")],
        snapshot=_snapshot(equity="1120.00"),
    )

    result = _analytics(conn)

    assert Decimal(result["avg_exposure"]) >= Decimal("0.00")
    assert Decimal(result["max_exposure"]) == Decimal("120.00")


def test_zero_length_or_missing_end_time_falls_back_to_the_book():
    """No clock spread to integrate: report the book rather than dividing by zero."""
    conn = _StubConnection(
        fills=[_fill("BUY", "1", "100", 0)],
        positions=[_position("1", "100.00")],
        snapshot=_snapshot(equity="1100.00", last_reconciled_at=STARTED_AT),
    )

    result = _analytics(conn)

    assert Decimal(result["avg_exposure"]) == Decimal("100.00")
    assert Decimal(result["max_exposure"]) == Decimal("100.00")
    assert Decimal(result["max_drawdown"]) == Decimal("0.00")


def test_fees_reduce_realized_pnl_and_the_drawdown_that_follows():
    """A losing roundtrip with a fee is a deeper trough, not a shallower one."""
    conn = _StubConnection(
        fills=[_fill("BUY", "1", "100", 20, fee="1"), _fill("SELL", "1", "40", 60, fee="1")],
        positions=[_position("0", "0")],
        snapshot=_snapshot(equity="938.00"),
    )

    result = _analytics(conn)

    assert Decimal(result["pnl_realized"]) == Decimal("-62.00")
    assert Decimal(result["max_drawdown"]) == Decimal("62.00")