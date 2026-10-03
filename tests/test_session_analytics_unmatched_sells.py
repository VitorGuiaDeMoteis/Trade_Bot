"""Regression: a SELL with no BUY lot must not vanish from session analytics.

`get_session_analytics` runs a per-symbol FIFO match over the run's fills to
build `closed_trades` and `pnl_realized`. A SELL whose BUY lot is not in the
same run (position opened in an earlier run, or a partially matched sell) used
to have its leftover `sell_qty` silently discarded at the end of the while
loop: no closed trade, no realized P&L, and no record that anything was
dropped. The reported session P&L then under-stated reality with nothing in
the payload to explain the gap.

These tests pin the fix: the unmatched quantity is accumulated per symbol and
reported under `anomalies.unmatched_sells`, while realized P&L is still
derived only from genuinely matched lots (an unknown cost basis is never
invented). `get_session_analytics` is called directly against a stub
connection that dispatches on the statement being executed, so no Postgres is
required.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from services.api.analytics import get_session_analytics

NOW = datetime.now(UTC)
BUY_AT = NOW - timedelta(hours=2)
SELL_AT = NOW - timedelta(hours=1)


def _buy(symbol: str, quantity: str, price: str, *, fee: str | None = None) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-buy-{symbol}",
        "symbol": symbol,
        "side": "BUY",
        "quantity": Decimal(quantity),
        "price": Decimal(price),
        "fee": Decimal(fee) if fee is not None else None,
        "filled_at": BUY_AT,
    }


def _sell(symbol: str, quantity: str, price: str, *, fee: str | None = None) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-sell-{symbol}",
        "symbol": symbol,
        "side": "SELL",
        "quantity": Decimal(quantity),
        "price": Decimal(price),
        "fee": Decimal(fee) if fee is not None else None,
        "filled_at": SELL_AT,
    }


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)

    def scalar(self) -> Any:
        """Unwrap the single selected column, as SQLAlchemy's Result.scalar does."""
        return next(iter(self._rows[0].values())) if self._rows else None


class _StubConnection:
    """Serves canned rows by inspecting which table each statement targets."""

    def __init__(
        self,
        fills: list[dict[str, Any]],
        *,
        positions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._fills = fills
        self._positions = positions or []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        text = str(statement)
        if "paper_runs" in text:
            return _Result(
                [{"created_at": BUY_AT - timedelta(days=1), "initial_cash": Decimal("1000")}]
            )
        if "MAX(last_reconciled_at)" in text:
            return _Result([{"end_time": NOW}])
        if "broker_fills" in text:
            return _Result(self._fills)
        if "broker_positions" in text:
            return _Result(self._positions)
        if "broker_portfolio_snapshots" in text:
            return _Result([{"cash": Decimal("1000"), "equity": Decimal("1000")}])
        if "paper_orders" in text:
            return _Result([])
        if "risk_decisions" in text:
            return _Result([])
        raise AssertionError(f"unexpected statement: {text}")

    def scalar(self, statement: Any) -> Any:
        raise AssertionError(f"unexpected scalar statement: {statement}")


def _analytics(fills: list[dict[str, Any]]) -> dict[str, Any]:
    return get_session_analytics(_StubConnection(fills), "run-1")  # type: ignore[arg-type]


def test_sell_with_no_buy_lot_is_reported_not_dropped() -> None:
    """A SELL whose BUY predates the run is surfaced, and invents no P&L."""
    result = _analytics([_sell("AAPL", "2", "20", fee="1")])

    assert result["anomalies"]["unmatched_sells"] == [{"symbol": "AAPL", "quantity": "2"}]
    # No cost basis exists, so nothing is realized -- but the drop is now visible.
    assert float(result["pnl_realized"]) == 0.0
    assert result["closed_trades"] == []
    assert result["trades_completed"] == 0


def test_partially_matched_sell_reports_only_the_remainder() -> None:
    """Matched lots still realize; only the unmatched leftover is reported."""
    result = _analytics([_buy("AAPL", "1", "10", fee="1"), _sell("AAPL", "3", "20", fee="2")])

    # 1 lot matched: (20-10)*1 - 1 (full buy fee) - 2/3 (pro-rata sell fee).
    assert float(result["pnl_realized"]) == 10 - 1 - (2 / 3)
    assert len(result["closed_trades"]) == 1
    assert result["anomalies"]["unmatched_sells"] == [{"symbol": "AAPL", "quantity": "2"}]


def test_multiple_unmatched_sells_on_one_symbol_accumulate() -> None:
    result = _analytics([_sell("TSLA", "1", "30"), _sell("TSLA", "2", "31")])

    assert result["anomalies"]["unmatched_sells"] == [{"symbol": "TSLA", "quantity": "3"}]


def test_fully_matched_sells_report_no_unmatched_quantity() -> None:
    """Control: the happy path stays silent (regression against over-reporting)."""
    result = _analytics([_buy("AAPL", "2", "10"), _sell("AAPL", "2", "20")])

    assert result["anomalies"]["unmatched_sells"] == []
    assert float(result["pnl_realized"]) == 20.0
    assert len(result["closed_trades"]) == 1


def test_unmatched_sell_does_not_consume_another_symbols_lot() -> None:
    """An unmatched symbol must not be matched against a different symbol's lot."""
    result = _analytics([_buy("AAPL", "1", "10"), _sell("TSLA", "1", "20")])

    assert result["anomalies"]["unmatched_sells"] == [{"symbol": "TSLA", "quantity": "1"}]
    assert result["closed_trades"] == []
    assert float(result["pnl_realized"]) == 0.0


def test_open_buy_lot_is_not_an_unmatched_sell() -> None:
    """A still-open BUY lot is a position, not an anomaly."""
    result = _analytics([_buy("AAPL", "1", "10")])

    assert result["anomalies"]["unmatched_sells"] == []
    assert result["closed_trades"] == []