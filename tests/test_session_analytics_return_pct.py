"""Regression: `return_pct` must be the documented ACCOUNT return.

docs/M4_CORE.md:67 defines the session return as

    return_pct = (equity final - initial cash) / initial cash * 100

but `get_session_analytics` computed it from `total_pnl` (this run's matched FIFO
realized P&L + the unrealized P&L of the CURRENT position book). The two
disagree whenever cash moved for a reason the fill walk cannot see:

- an unmatched SELL has no local BUY lot, so its P&L is deliberately not
  realized (see `anomalies.unmatched_sells`) and the account's loss vanishes;
- a lot inherited from a previous run opens or closes inside this session;
- fees settle, or cash is deposited, with no fill to explain it.

In every one of those cases `return_pct` reported the P&L number while
`equity_initial`/`equity_final` in the same payload told a different story.

These tests drive `get_session_analytics` against a stub connection (no Postgres)
and pin that the numerator is the equity difference, with a CONTROL where the
two agree so the fix cannot be read as "always report the equity".
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from services.api.analytics import get_session_analytics

NOW = datetime.now(UTC)
AT = NOW - timedelta(hours=2)

INITIAL_CASH = Decimal("1000")


def _fill(symbol: str, side: str, quantity: str, price: str) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-{side}-{symbol}",
        "symbol": symbol,
        "side": side,
        "quantity": Decimal(quantity),
        "price": Decimal(price),
        "fee": None,
        "filled_at": AT,
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
        return next(iter(self._rows[0].values())) if self._rows else None


class _StubConnection:
    """Serves canned rows, keyed on which table each statement targets."""

    def __init__(self, fills: list[dict[str, Any]], equity: str, cash: str = "0") -> None:
        self._fills = fills
        self._equity = equity
        self._cash = cash

    def execute(self, statement: Any, params: Any = None) -> _Result:
        text = str(statement)
        if "paper_runs" in text:
            # `provider` is NOT NULL on paper_runs and scopes every broker-owned read below.
            return _Result(
                [
                    {
                        "created_at": AT - timedelta(days=1),
                        "initial_cash": INITIAL_CASH,
                        "provider": "alpaca",
                    }
                ]
            )
        if "MAX(last_reconciled_at)" in text:
            return _Result([{"end_time": NOW}])
        if "broker_fills" in text:
            return _Result(self._fills)
        if "broker_positions" in text:
            return _Result([])
        if "broker_portfolio_snapshots" in text:
            return _Result([{"cash": self._cash, "equity": self._equity}])
        if "paper_orders" in text:
            return _Result([])
        if "risk_decisions" in text:
            return _Result([])
        raise AssertionError(f"unexpected statement: {text}")

    def scalar(self, statement: Any) -> Any:
        raise AssertionError(f"unexpected scalar statement: {statement}")


def _analytics(fills: list[dict[str, Any]], equity: str) -> dict[str, Any]:
    return get_session_analytics(_StubConnection(fills, equity), "run-1")  # type: ignore[arg-type]


def test_return_pct_is_the_equity_difference_not_the_matched_pnl() -> None:
    """A +20 matched round trip on an account that lost 10% still reports -10%."""
    result = _analytics(
        [_fill("AAPL", "BUY", "1", "10"), _fill("AAPL", "SELL", "1", "30")],
        equity="900",
    )

    assert float(result["pnl_realized"]) == 20.0
    assert result["equity_initial"] == str(INITIAL_CASH)
    assert result["equity_final"] == "900"
    assert float(result["return_pct"]) == -10.0
    # Explicitly not the old P&L-based numerator: 20 / 1000.
    assert float(result["return_pct"]) != 2.0


def test_unmatched_sell_loss_still_shows_in_the_session_return() -> None:
    """No BUY lot -> no realized P&L, but the account still lost the cash."""
    result = _analytics([_fill("AAPL", "SELL", "1", "30")], equity="970")

    assert float(result["pnl_realized"]) == 0.0
    assert result["anomalies"]["unmatched_sells"] == [{"symbol": "AAPL", "quantity": "1"}]
    assert float(result["return_pct"]) == -3.0


def test_inherited_lot_closing_inside_the_session_is_counted() -> None:
    """A gain on a lot this run never bought still moved the account."""
    result = _analytics([_fill("AAPL", "SELL", "1", "30")], equity="1030")

    assert float(result["pnl_realized"]) == 0.0
    assert float(result["return_pct"]) == 3.0


def test_control_equity_and_pnl_agree_leaves_the_return_unchanged() -> None:
    """When the account moved by exactly the matched P&L, both formulas agree."""
    result = _analytics(
        [_fill("AAPL", "BUY", "1", "10"), _fill("AAPL", "SELL", "1", "30")],
        equity="1020",
    )

    assert float(result["pnl_total"]) == 20.0
    assert float(result["return_pct"]) == 2.0


def test_flat_account_reports_zero_return() -> None:
    """No movement at all: neither formula may invent a return."""
    result = _analytics(
        [_fill("AAPL", "BUY", "1", "10"), _fill("AAPL", "SELL", "1", "10")],
        equity="1000",
    )

    assert float(result["pnl_total"]) == 0.0
    assert float(result["return_pct"]) == 0.0
