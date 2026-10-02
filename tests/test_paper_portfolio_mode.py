"""Regression: the simulator portfolio must report the run's real `mode`.

`paper_queries.portfolio` is the SECOND constructor of `PaperPortfolio` (the
first is the broker route in `broker_routes.py`). It read `status` and
`provider` off the `paper_runs` row but never `mode`, so the contract default
("REPLAY") was published no matter which run was actually active.

That is not a harmless default. `paper_runs.mode` is CHECK-constrained to
REPLAY|alpaca_paper, and `/api/v1/paper/portfolio` serves whatever run
`system_controls.active_run_id` points at -- including an alpaca_paper run,
which is exactly what this deployment runs. So the endpoint labelled a live
alpaca_paper book "REPLAY" while the sibling broker route reported
"alpaca_paper" for the same money. An operator cannot tell from the payload
which executor produced the numbers, and `mode` is the field that says so.

No Postgres here: `portfolio()` is called directly against a stub connection
that dispatches on the statement being executed, mirroring the broker-route
tests.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from packages.domain.paper import PaperConfig
from services.api.paper_queries import portfolio

NOW = datetime.now(UTC)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def one(self) -> dict[str, Any]:
        """`paper_runs` is fetched with .one() -- the row is guaranteed to exist."""
        return self._rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def __iter__(self) -> "Iterator[dict[str, Any]]":
        # `portfolio` iterates `.mappings()` directly for the marks query, so a
        # bare `.first()`/`.one()`/`.all()` stand-in is not enough.
        return iter(self._rows)


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class _StubConnection:
    """Serves canned rows by inspecting which table each statement targets."""

    def __init__(self, *, control: dict[str, Any] | None, run: dict[str, Any] | None) -> None:
        self._control = control
        self._run = run
        self.statements: list[str] = []

    def execute(self, statement: Any) -> _Result:
        text = str(statement)
        self.statements.append(text)
        if "system_controls" in text:
            return _Result([self._control] if self._control else [])
        if "paper_runs" in text:
            return _Result([self._run] if self._run else [])
        # positions / marks / orders / fills: an empty book is enough here --
        # this defect is in the constructor's field mapping, not the list build.
        return _Result([])

    def scalar(self, statement: Any) -> int:
        self.statements.append(str(statement))
        return 0


def _run_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "run_id": uuid4(),
        "status": "ACTIVE",
        "mode": "REPLAY",
        "provider": "local",
        "started_at": NOW - timedelta(hours=1),
        "as_of": NOW - timedelta(minutes=1),
        "step": 42,
        "fee_bps": Decimal("1"),
        "slippage_bps": Decimal("5"),
        "dataset_hash": "sha256:" + "a" * 64,
        "dataset": ({"kind": "inline", "rows": 3},),
    }
    row.update(overrides)
    return row


class _StubStore:
    """Minimal PaperStore stand-in: the constructor only touches config/settings."""

    def __init__(self) -> None:
        self.config = PaperConfig(initial_cash=Decimal("10000"))
        self.settings = SimpleNamespace(market_data_provider="local")

    def reconcile(self, c: Any, run: dict[str, Any]) -> Any:
        from packages.domain.paper import PaperBook

        book = PaperBook(initial_cash=Decimal("10000"), cash=Decimal("10000"))
        book.reconcile()
        return book


def _call(conn: _StubConnection) -> Any:
    # Stubs stand in for a real Connection/PaperStore; the route is called
    # directly, so the annotations are deliberately widened.
    return portfolio(cast(Any, conn), cast(Any, _StubStore()))


def test_portfolio_reports_the_runs_real_mode_not_the_contract_default() -> None:
    """An ALPACA_PAPER run must be published as ALPACA_PAPER.

    The stored value is uppercase because `ck_paper_run_mode` at migration head
    f2c8a51d9b10 is `mode IN ('REPLAY','ALPACA_PAPER')`, which is exactly the
    `PaperPortfolio.mode` Literal -- so the column needs no translation.
    """
    run = _run_row(mode="ALPACA_PAPER")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": run["run_id"]},
        run=run,
    )

    result = _call(conn)

    # The test has teeth: the default and the truth really are different values.
    assert result.mode == "ALPACA_PAPER"
    assert result.mode != "REPLAY"


def test_replay_run_still_reports_replay() -> None:
    """The fix reads the column; it does not blanket-stamp one value."""
    run = _run_row(mode="REPLAY")
    conn = _StubConnection(
        control={"paused": False, "active_run_id": run["run_id"]},
        run=run,
    )

    assert _call(conn).mode == "REPLAY"


def test_no_active_run_reports_the_unguarded_default() -> None:
    """With no run there is no row to read, so the constructor's default stands."""
    conn = _StubConnection(control={"paused": False, "active_run_id": None}, run=None)

    assert _call(conn).mode == "REPLAY"
