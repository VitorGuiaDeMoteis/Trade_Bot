"""Pending execution must never be sized without the broker's own account/positions.

`AlpacaPaperWorker._process_pending_submits` (worker.py:376) refuses to submit
whenever there IS an approved-but-unsubmitted risk decision and the caller did not
hand it the broker account and position payloads:

    pending = await asyncio.to_thread(fetch_pending)
    if not pending:
        return
    if account is None or positions is None:
        raise RuntimeError("broker_state_not_supplied_to_execution")

The reason this is a safety guarantee rather than a diagnostic: the sizing path
below it needs broker state to decide. `last_equity` feeds the daily-loss breaker
(worker.py:385) and `positions` feeds the guard's available-quantity check, so
sizing without them either silently disables the breaker -- the failure mode the
`last_equity` comment above explicitly exists to prevent -- or sizes a SELL
against an unknown book. Raising fails the cycle closed: `_run` catches it and
calls `_enter_degraded`, and a degraded worker releases no further execution for
the rest of the process lifetime.

Two boundaries matter and both are pinned below:

- the guard fires ONLY on non-empty pending work. A quiet cycle must return
  before it, or every paused/idle system would degrade itself for having no
  broker payload;
- the per-cycle gate still comes FIRST. A degraded or not-yet-reconciled worker
  returns without touching the database at all, so the guard cannot be reached in
  a state where it would raise on stale conditions.

Nothing here needs Postgres, the broker or a real engine: `fetch_pending` is one
scripted read of `system_controls` followed by one scripted read of the pending
query, and the guard is checked before any submission happens.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from services.alpaca_paper.guard import ExecutionGuard
from services.alpaca_paper.worker import AlpacaPaperWorker

RUN_ID = "run-1"


class _Result:
    """Canned result for one scripted statement."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> "_Result":
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _ScriptedConnection:
    """Serves the control row first, then the pending-decision rows.

    `fetch_pending` issues exactly two statements in that order: the
    `system_controls` read that decides whether there is an active run, and the
    APPROVED-decisions-with-no-order query.
    """

    def __init__(self, control: Any, pending: list[Any]) -> None:
        self._control = control
        self._pending = pending
        self.calls = 0

    def execute(self, statement, *args, **kwargs) -> _Result:
        self.calls += 1
        return _Result([self._control] if self.calls == 1 else self._pending)

    def scalars(self, statement, *args, **kwargs) -> list[Any]:
        """The blocked-symbols read; no recently rejected order in these tests."""
        return []

    def __enter__(self) -> "_ScriptedConnection":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class _ScriptedEngine:
    def __init__(self, connection: _ScriptedConnection) -> None:
        self.connection = connection

    def connect(self) -> _ScriptedConnection:
        return self.connection

    def begin(self) -> _ScriptedConnection:
        return self.connection


def _worker(
    *,
    pending: list[Any],
    paused: bool = False,
    active_run_id: str | None = RUN_ID,
) -> tuple[AlpacaPaperWorker, _ScriptedConnection]:
    connection = _ScriptedConnection(
        {"paused": paused, "active_run_id": active_run_id}, pending
    )
    worker = AlpacaPaperWorker(_ScriptedEngine(connection), None, None)  # type: ignore[arg-type]
    # Open the execution gate; the worker starts degraded and unreconciled by
    # design, which is exercised separately below.
    worker.degraded = False
    worker.reconciliation_ready = True
    return worker, connection


def _pending_row() -> dict[str, Any]:
    """One APPROVED decision that has not produced a paper order yet."""
    return {
        "run_id": RUN_ID,
        "decision_id": "d-1",
        "signal_id": "s-1",
        "decision": "APPROVED",
        "reason": "entry",
        "decided_at": datetime(2026, 10, 2, 19, 1, tzinfo=UTC),
        "signal_type": "BUY",
        "symbol": "AAPL",
    }


def _submit(worker: AlpacaPaperWorker, **kwargs) -> None:
    asyncio.run(worker._process_pending_submits(**kwargs))


def test_pending_buy_without_account_raises():
    """The daily-loss breaker reads `account`; no account means no breaker."""
    worker, _ = _worker(pending=[_pending_row()])
    with pytest.raises(RuntimeError, match="broker_state_not_supplied_to_execution"):
        _submit(worker, account=None, positions=[])


def test_pending_sell_without_positions_raises():
    """A SELL is sized from available quantity, which comes from `positions`."""
    worker, _ = _worker(pending=[_pending_row()])
    with pytest.raises(RuntimeError, match="broker_state_not_supplied_to_execution"):
        _submit(worker, account={"equity": "100000"}, positions=None)


def test_supplied_payloads_reach_the_sizing_path(monkeypatch):
    """The CONTROL: `positions == []` is a real broker answer (flat book).

    The guard tests for None, so an empty book passes it -- refusing to trade on
    a genuinely flat account would strand the first entry of every session. To
    assert the call really got past the guard (instead of merely "did not raise"),
    `ExecutionGuard.evaluate` is captured: it is the first consumer of both
    payloads, so seeing them proves the guard let them through to sizing.
    """
    captured: dict[str, Any] = {}

    def fake_evaluate(**kwargs: Any) -> tuple[bool, str]:
        captured.update(kwargs)
        # Reject without submitting, so no adapter call is attempted.
        return False, "captured_by_test"

    monkeypatch.setattr(ExecutionGuard, "evaluate", staticmethod(fake_evaluate))

    worker, _ = _worker(pending=[_pending_row()])
    _submit(worker, account={"equity": "100000", "last_equity": "99000"}, positions=[])

    assert captured["positions"] == []
    assert captured["snapshot"] == {"equity": "100000", "last_equity": "99000"}
    assert captured["last_equity"] == Decimal("99000")


def test_no_pending_work_returns_before_the_guard():
    """A quiet cycle must not degrade itself for lack of a broker payload."""
    worker, _ = _worker(pending=[])
    _submit(worker, account=None, positions=None)


def test_paused_or_runless_control_returns_before_the_guard():
    """With no active run there is no execution to protect, so no raise."""
    for paused, active in ((True, RUN_ID), (False, None)):
        worker, _ = _worker(pending=[_pending_row()], paused=paused, active_run_id=active)
        _submit(worker, account=None, positions=None)


def test_degraded_worker_returns_without_reading_the_database():
    """The per-cycle gate precedes the guard, so it wins even with pending work."""
    worker, connection = _worker(pending=[_pending_row()])
    worker.degraded = True
    _submit(worker, account=None, positions=None)
    assert connection.calls == 0


def test_unreconciled_worker_returns_without_reading_the_database():
    worker, connection = _worker(pending=[_pending_row()])
    worker.reconciliation_ready = False
    _submit(worker, account=None, positions=None)
    assert connection.calls == 0