"""The REPLAY portfolio must never publish `reconciled` by inheritance.

`PaperPortfolio.reconciled` defaults to True, and
`paper_queries.portfolio()` builds a portfolio from the store's configured
opening balance before it has reconciled anything. Before this fix the
constructor never set the field, so BOTH return paths published the contract
default:

* no active run -> the opening-balance book was published as reconciled;
* active run -> the flag was "accidentally right", but only because the
  default happened to match, which is indistinguishable in the payload from
  the unreconciled case above.

This is the sibling defect of the broker-route fix in fbdbac1
(`test_failed_reconciliation_is_never_published_as_reconciled`): a defaulted
contract field is an UNSET field, not a neutral one. A consumer that trusts
`reconciled` -- and many will, since True is the default -- would read the
REPLAY book as verified against the runtime database when it was never
reconciled at all.

The harness mirrors tests/test_paper_portfolio_mode.py: the defect is in the
constructor's field mapping, not in the book build, so an empty book is
enough and no runtime database is touched.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from packages.domain.paper import PaperBook, PaperConfig
from services.api.paper_queries import portfolio

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def one(self) -> dict[str, Any]:
        assert self._rows, "expected exactly one row"
        return self._rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def __iter__(self) -> "Iterator[dict[str, Any]]":
        # `portfolio` iterates `.mappings()` directly for the marks/orders/fills
        # queries, so a bare .first()/.one()/.all() stand-in is not enough.
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
        # positions / marks / orders / fills: an empty book is enough here.
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
    """Minimal PaperStore stand-in: only config/settings/reconcile are touched."""

    def __init__(self) -> None:
        self.config = PaperConfig(initial_cash=Decimal("10000"))
        self.settings = SimpleNamespace(market_data_provider="local")

    def reconcile(self, c: Any, run: dict[str, Any]) -> Any:
        book = PaperBook(initial_cash=Decimal("10000"), cash=Decimal("10000"))
        book.reconcile()
        return book


def _call(conn: _StubConnection) -> Any:
    # Stubs stand in for a real Connection/PaperStore; the query function is
    # called directly, so the annotations are deliberately widened.
    return portfolio(cast(Any, conn), cast(Any, _StubStore()))


def test_no_active_run_is_never_published_as_reconciled() -> None:
    """The opening-balance book was never reconciled -> reconciled must be False.

    This is the regression: the contract defaults `reconciled` to True, and
    the constructor left it unset, so this payload was published as
    `"reconciled": true` over a book that is nothing but the configured
    opening balance.
    """
    conn = _StubConnection(control={"paused": False, "active_run_id": None}, run=None)

    result = _call(conn)

    # The test has teeth: the default and the truth really are different values.
    assert result.reconciled is False
    assert result.reconciled is not True
    # No reconcile happened, so there is no reconcile timestamp to report.
    assert result.last_reconciled_at is None


def test_absent_control_row_is_never_published_as_reconciled() -> None:
    """No control row at all is the same unreconciled case, not a neutral one."""
    conn = _StubConnection(control=None, run=None)

    assert _call(conn).reconciled is False


def test_active_run_still_reports_reconciled_with_a_stamp() -> None:
    """The control: a genuine reconcile must still report reconciled=True.

    The fix stamps the flag from the reconcile, so this path must not flip to
    False -- a blanket `reconciled = False` would be equally wrong.
    """
    run = _run_row()
    conn = _StubConnection(
        control={"paused": False, "active_run_id": run["run_id"]},
        run=run,
    )

    result = _call(conn)

    assert result.reconciled is True
    # A reconciled portfolio without a timestamp cannot be aged by a consumer.
    assert result.last_reconciled_at is not None
    assert result.last_reconciled_at.tzinfo is not None


def test_reconciled_is_not_inherited_from_the_contract_default() -> None:
    """The flag is set on every path, so the contract default is unreachable.

    Guards the mechanism, not the payload: if a future edit drops either
    assignment, this fails even though the two tests above still pass (they
    assert one path each).
    """
    from packages.contracts.paper import PaperPortfolio

    # `PaperPortfolio` is a Pydantic model, so the defaults live in
    # `model_fields`, not `__dataclass_fields__`.
    assert PaperPortfolio.model_fields["reconciled"].default is True
    assert PaperPortfolio.model_fields["last_reconciled_at"].default is None

    run = _run_row()
    cases = (
        # No active run -> nothing reconciled.
        _StubConnection(control={"paused": False, "active_run_id": None}, run=None),
        # Active run -> the book was reconciled against the durable tables.
        _StubConnection(control={"paused": False, "active_run_id": run["run_id"]}, run=run),
    )
    for conn in cases:
        # Either way, exactly one of the two stamps must be present and the
        # flag must agree with it -- no third "unset" outcome exists.
        result = _call(conn)
        stamped = result.last_reconciled_at is not None
        assert result.reconciled is stamped
