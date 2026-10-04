"""Regression: every broker-owned read must be scoped to the run's own provider.

`broker_portfolio_snapshots` (primary key `provider`) and `broker_positions`
(primary key `provider`, `symbol`) hold PER-PROVIDER account state -- a
simulator account and the Alpaca paper account are separate rows in the same
tables. Three of the reads in `get_session_analytics` were unscoped, so with
both providers registered one session's P&L silently mixed in the other's
account:

- `MAX(last_reconciled_at)` took the max across providers, so `ended_at`
  reported the OTHER account's reconciliation time;
- the position aggregate summed every provider's rows into this run's
  unrealized P&L, market value and exposure;
- the snapshot read (`... LIMIT 1`) landed on an arbitrary row, because row
  order is not guaranteed, and could return another provider's equity as
  `equity_final` -- corrupting `return_pct` too.

The stub below serves rows from BOTH providers and only filters them when the
statement actually carries `provider = :provider`, so dropping the WHERE
clause again reproduces the mixed numbers instead of silently passing. A
CONTROL run whose own provider is the other one pins that the scoping follows
the run row rather than hardcoding one account.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from services.api.analytics import get_session_analytics

NOW = datetime.now(UTC)
STARTED_AT = NOW - timedelta(hours=3)

INITIAL_CASH = Decimal("1000")

ALPACA = "alpaca"
SIMULATOR = "simulator"

# The other account is deliberately larger and currently LOSING money: an
# unscoped aggregate would net its loss into this run's unrealized P&L.
ALPACA_POSITIONS = [
    {
        "provider": ALPACA,
        "symbol": "AAPL",
        "quantity": Decimal("1"),
        "average_price": Decimal("180"),
        "current_price": Decimal("200"),
        "market_value": Decimal("200"),
        "unrealized_pnl": Decimal("20"),
        "updated_at": NOW,
    }
]
OTHER_POSITIONS = [
    {
        "provider": SIMULATOR,
        "symbol": "MSFT",
        "quantity": Decimal("3"),
        "average_price": Decimal("400"),
        "current_price": Decimal("350"),
        "market_value": Decimal("300"),
        "unrealized_pnl": Decimal("-150"),
        "updated_at": NOW,
    }
]

ALPACA_SNAPSHOT: dict[str, Any] = {
    "cash": Decimal("1000"),
    "equity": Decimal("1020"),
    "last_reconciled_at": NOW,
}
# Reconciled LATER than alpaca's, and carrying a far larger equity.
OTHER_SNAPSHOT: dict[str, Any] = {
    "cash": Decimal("7000"),
    "equity": Decimal("8000"),
    "last_reconciled_at": NOW + timedelta(minutes=30),
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


class _TwoProviderStubConnection:
    """Serves both accounts, filtered only when the statement scopes them."""

    def __init__(self, run_provider: str = ALPACA) -> None:
        self._run_provider = run_provider
        self._own = ALPACA if run_provider == ALPACA else SIMULATOR
        self._other = SIMULATOR if run_provider == ALPACA else ALPACA

    def _scoped(self, sql: str, params: Any) -> bool:
        return (
            bool(params)
            and params.get("provider") == self._own
            and "provider = :provider" in sql
        )

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = str(statement)
        if "paper_runs" in sql:
            return _Result(
                [
                    {
                        "created_at": STARTED_AT,
                        "initial_cash": INITIAL_CASH,
                        "provider": self._run_provider,
                    }
                ]
            )
        if "MAX(last_reconciled_at)" in sql:
            # Unscoped, MAX spans both accounts and the later one wins.
            end = self._own_snapshot() if self._scoped(sql, params) else OTHER_SNAPSHOT
            return _Result([{"end_time": end["last_reconciled_at"]}])
        if "broker_positions" in sql:
            if self._scoped(sql, params):
                return _Result([self._own_row()])
            return _Result([self._own_row(), self._other_row()])
        if "broker_portfolio_snapshots" in sql:
            if self._scoped(sql, params):
                return _Result([self._own_snapshot()])
            # Unscoped, the row order is arbitrary: serve the other account first
            # so a LIMIT 1 read demonstrably picks the wrong equity.
            return _Result([self._other_snapshot(), self._own_snapshot()])
        if "broker_fills" in sql:
            return _Result([])
        if "paper_orders" in sql:
            return _Result([])
        if "risk_decisions" in sql:
            return _Result([])
        raise AssertionError(f"unexpected statement: {sql}")

    def _own_row(self) -> dict[str, Any]:
        return ALPACA_POSITIONS[0] if self._own == ALPACA else OTHER_POSITIONS[0]

    def _other_row(self) -> dict[str, Any]:
        return OTHER_POSITIONS[0] if self._own == ALPACA else ALPACA_POSITIONS[0]

    def _own_snapshot(self) -> dict[str, Any]:
        return ALPACA_SNAPSHOT if self._own == ALPACA else OTHER_SNAPSHOT

    def _other_snapshot(self) -> dict[str, Any]:
        return OTHER_SNAPSHOT if self._own == ALPACA else ALPACA_SNAPSHOT


def _analytics(run_provider: str = ALPACA) -> dict[str, Any]:
    return get_session_analytics(_TwoProviderStubConnection(run_provider), "run-1")  # type: ignore[arg-type]


def test_unrealized_pnl_sums_only_the_runs_own_provider() -> None:
    """The other account is down 150; this run must not book that loss."""
    result = _analytics()

    assert float(result["pnl_unrealized"]) == 20.0
    # Not 20 + (-150).
    assert float(result["pnl_unrealized"]) != -130.0


def test_exposure_and_symbols_exclude_the_other_provider() -> None:
    """Exposure is an average over THIS account's book, not the union of both."""
    result = _analytics()

    assert float(result["avg_exposure"]) == 200.0
    assert float(result["max_exposure"]) == 200.0
    assert list(result["symbols_data"]) == ["AAPL"]
    assert result["anomalies"]["dust_positions"] == []


def test_equity_final_reads_the_runs_own_snapshot_row() -> None:
    """The other account holds 8000; reading its row would report +700%."""
    result = _analytics()

    assert result["equity_final"] == "1020"
    assert float(result["return_pct"]) == 2.0
    assert float(result["return_pct"]) != 700.0


def test_ended_at_is_this_providers_last_reconciliation() -> None:
    """MAX() unscoped returns the other account's later reconciliation."""
    result = _analytics()

    assert result["ended_at"] == ALPACA_SNAPSHOT["last_reconciled_at"].isoformat()


def test_control_scoping_follows_the_run_row_not_a_hardcoded_provider() -> None:
    """A run owned by the OTHER account reports that account's numbers."""
    result = _analytics(SIMULATOR)

    assert float(result["pnl_unrealized"]) == -150.0
    assert result["equity_final"] == "8000"
    assert result["ended_at"] == OTHER_SNAPSHOT["last_reconciled_at"].isoformat()