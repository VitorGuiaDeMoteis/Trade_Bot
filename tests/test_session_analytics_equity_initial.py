"""Regression: `equity_initial` must be the session's starting cash.

`broker_portfolio_snapshots` is a single-row-per-provider upsert table
(`provider` is the primary key, and the worker writes it with
`on_conflict_do_update`), NOT a time series. Every row therefore holds the
CURRENT broker equity, so the two snapshot reads in `get_session_analytics`
were returning the same value:

- `equity_initial` reported the current equity, and
- `equity_final` reported the same current equity,

which made `equity_initial == equity_final` for every session and left the
payload unable to express its own return. It also put the current equity in
the denominator of `return_pct` instead of the run's starting cash.

These tests pin the fix: the initial figure comes from `paper_runs.initial_cash`
(NOT NULL), the final figure stays the live snapshot, and a session with no
snapshot yet falls back to the starting cash for both. `get_session_analytics`
is called directly against a stub connection, so no Postgres is required.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from services.api.analytics import get_session_analytics

NOW = datetime.now(UTC)
BUY_AT = NOW - timedelta(hours=2)
SELL_AT = NOW - timedelta(hours=1)

INITIAL_CASH = Decimal("1000")
# The one live snapshot row: CURRENT equity, i.e. the session already made money.
SNAPSHOT_EQUITY = Decimal("1042.5")
SNAPSHOT_CASH = Decimal("970")


def _buy(symbol: str, quantity: str, price: str) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-buy-{symbol}",
        "symbol": symbol,
        "side": "BUY",
        "quantity": Decimal(quantity),
        "price": Decimal(price),
        "fee": None,
        "filled_at": BUY_AT,
    }


def _sell(symbol: str, quantity: str, price: str) -> dict[str, Any]:
    return {
        "broker_fill_id": f"fill-sell-{symbol}",
        "symbol": symbol,
        "side": "SELL",
        "quantity": Decimal(quantity),
        "price": Decimal(price),
        "fee": None,
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
        return next(iter(self._rows[0].values())) if self._rows else None


class _StubConnection:
    """Serves canned rows, keyed on which table each statement targets."""

    def __init__(
        self,
        fills: list[dict[str, Any]],
        *,
        snapshots: list[dict[str, Any]] | None = None,
        positions: list[dict[str, Any]] | None = None,
        initial_cash: Decimal | None = INITIAL_CASH,
    ) -> None:
        self._fills = fills
        self._snapshots = snapshots
        self._positions = positions or []
        self._initial_cash = initial_cash

    def execute(self, statement: Any, params: Any = None) -> _Result:
        text = str(statement)
        if "paper_runs" in text:
            row: dict[str, Any] = {"created_at": BUY_AT - timedelta(days=1)}
            if self._initial_cash is not None:
                row["initial_cash"] = self._initial_cash
            return _Result([row])
        if "MAX(last_reconciled_at)" in text:
            return _Result([{"end_time": NOW}])
        if "broker_fills" in text:
            return _Result(self._fills)
        if "broker_positions" in text:
            return _Result(self._positions)
        if "broker_portfolio_snapshots" in text:
            if self._snapshots is None:
                return _Result([{"cash": SNAPSHOT_CASH, "equity": SNAPSHOT_EQUITY}])
            return _Result(self._snapshots)
        if "paper_orders" in text:
            return _Result([])
        if "risk_decisions" in text:
            return _Result([])
        raise AssertionError(f"unexpected statement: {text}")

    def scalar(self, statement: Any) -> Any:
        raise AssertionError(f"unexpected scalar statement: {statement}")


def _analytics(
    fills: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    return get_session_analytics(_StubConnection(fills, **kwargs), "run-1")  # type: ignore[arg-type]


def test_equity_initial_is_the_runs_starting_cash_not_the_live_equity() -> None:
    """The snapshot is current-state, so it cannot be the session's opener."""
    result = _analytics([_buy("AAPL", "1", "10")])

    assert result["equity_initial"] == str(INITIAL_CASH)
    assert result["equity_final"] == str(SNAPSHOT_EQUITY)
    # The two figures must differ, otherwise no consumer can compute a return.
    assert result["equity_initial"] != result["equity_final"]


def test_return_pct_is_measured_against_the_starting_cash() -> None:
    """A +20 round trip on 1000 of starting cash is +2%, not ~1.96%.

    The snapshot equity is pinned to 1020 -- initial cash plus exactly the +20
    this round trip realized -- so the account and the P&L agree and the only
    thing under test is the DENOMINATOR. With the default SNAPSHOT_EQUITY the
    account and the P&L would disagree, and the reported return would then be
    the equity difference (see tests/test_session_analytics_return_pct.py, which
    pins that behaviour deliberately).
    """
    result = _analytics(
        [_buy("AAPL", "1", "10"), _sell("AAPL", "1", "30")],
        snapshots=[{"cash": "1000", "equity": "1020"}],
    )

    assert float(result["pnl_realized"]) == 20.0
    assert float(result["return_pct"]) == 2.0
    # Guard against the old denominator: 20 / 1020 (the live equity).
    assert float(result["return_pct"]) != 20.0 / 1020.0 * 100


def test_equity_final_still_tracks_the_live_snapshot() -> None:
    """Control: only the initial figure changed, the final one is untouched."""
    result = _analytics([_buy("AAPL", "1", "10")])

    assert result["equity_final"] == str(SNAPSHOT_EQUITY)
    assert result["equity_final"] != result["equity_initial"]


def test_session_without_a_snapshot_falls_back_to_starting_cash() -> None:
    """Before the first reconcile both ends of the session are the start cash."""
    result = _analytics([_buy("AAPL", "1", "10")], snapshots=[])

    assert result["equity_initial"] == str(INITIAL_CASH)
    assert result["equity_final"] == str(INITIAL_CASH)
    assert float(result["return_pct"]) == 0.0
