"""A broker/local divergence must abort the WHOLE cycle, not one order.

The worker has two different blast radii for faults, and the difference is
deliberate. Pinning the account-wide half of it here, because only the
per-order half was pinned (test_worker_reconcile_isolates_bad_order.py):

- `_reconcile_active_orders` (worker.py:581) CATCHES a RuntimeError per order
  and keeps going. A single order whose broker numerics cannot be sourced must
  not stop the bot: that order stays in ACTIVE_ORDER_STATUSES, no fabricated 0
  is written, and every OTHER order still gets its fills recorded.

- `_assert_open_orders_known` (worker.py:150) is NOT wrapped and must NOT be.
  It answers a different question: "is the broker's whole open-order book
  known to us?". Its failure modes are account-wide by construction, not
  per-order:

    * an open order with no local row means some unknown order is live and
      working against the account. There is no "skip it and carry on" that
      keeps the bot safe, because we cannot size new orders without knowing
      what is already outstanding;
    * a status divergence means an order the bot considers terminal is still
      live at the broker -- the double-exposure shape, where sizing from the
      local picture oversells on the next cycle;
    * a symbol/side divergence means every position derived from that row is
      wrong, not just that row.

  Scoping any of these to one order would leave the remaining orders verified
  against a picture we have already proven is wrong, and then the cycle would
  go on to `_save_broker_snapshot` (worker.py:151) and flip
  `reconciliation_ready`/`has_reconciled` to True. That would OPEN the
  execution gate on an unverified broker picture: a fail-OPEN, strictly worse
  than the availability cost of degrading.

So the contract pinned below is: the raise escapes `reconcile_once` entirely,
the snapshot is never written, and the gate stays shut. `_run`'s handler then
calls `_enter_degraded`, which releases no further execution for the life of
the process -- costly, but the correct side to err on for a trading-safety
invariant.

Pure unit test: no Postgres, no broker, no DB mutation. `reconcile_once` drives
the adapter and the engine only, both stubbed here; `_reconcile_active_orders`
is stubbed out so this test exercises the account-wide step alone.
"""

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from services.alpaca_paper.worker import AlpacaPaperWorker

BROKER_ID = "b-123"
CLIENT_ID = "c-123"


def _local_row(
    *,
    broker_order_id: str | None = BROKER_ID,
    client_order_id: str | None = CLIENT_ID,
    symbol: str = "AAPL",
    side: str = "BUY",
    status: str = "NEW",
    requested_notional: Any = None,
    requested_quantity: Any = None,
) -> dict[str, Any]:
    """One row of the broker_orders JOIN paper_orders read the worker performs."""
    return {
        "broker_order_id": broker_order_id,
        "client_order_id": client_order_id,
        "requested_notional": requested_notional,
        "requested_quantity": requested_quantity,
        "symbol": symbol,
        "side": side,
        "status": status,
    }


def _remote_order(
    *,
    order_id: str | None = BROKER_ID,
    client_order_id: str | None = CLIENT_ID,
    symbol: str = "AAPL",
    side: str = "BUY",
    notional: Any = None,
    qty: Any = None,
) -> dict[str, Any]:
    """An order as returned by the broker's open-orders endpoint."""
    return {
        "id": order_id,
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
        "notional": notional,
        "qty": qty,
    }


class _ScriptedResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> "_ScriptedResult":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _ScriptedConnection:
    """Serves the canned local rows the account-wide assert reads.

    `execute()` is never called for a snapshot write in these tests: reaching
    that write is the failure these tests are pinning, so the snapshot is
    recorded as a call instead of being carried out.
    """

    def __init__(self, rows: list[Any], snapshot_writes: list[Any]) -> None:
        self._rows = rows
        self._snapshot_writes = snapshot_writes

    def execute(self, statement, *args, **kwargs) -> _ScriptedResult:
        return _ScriptedResult(self._rows)

    def scalars(self, statement, *args, **kwargs):
        # `_reconcile_active_orders` is stubbed out; this only keeps a stray
        # scalar read from crashing on a missing method.
        return iter(())

    def __enter__(self) -> "_ScriptedConnection":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class _ScriptedEngine:
    def __init__(self, rows: list[Any], snapshot_writes: list[Any]) -> None:
        self._rows = rows
        self._snapshot_writes = snapshot_writes

    def connect(self) -> _ScriptedConnection:
        return _ScriptedConnection(self._rows, self._snapshot_writes)

    def begin(self) -> _ScriptedConnection:
        return _ScriptedConnection(self._rows, self._snapshot_writes)


class _ScriptedAdapter:
    """An ACTIVE account whose open-order book is the caller's."""

    def __init__(self, open_orders: list[dict[str, Any]]) -> None:
        self._open_orders = open_orders

    async def get_account(self) -> dict[str, Any]:
        # Complete enough for `_save_broker_snapshot`, which reads every
        # monetary field unconditionally and fails closed on a missing one
        # (`invalid_broker_cash`). The control tests below need a cycle that
        # reaches that write; a half-built account would raise there and make
        # them assert the writer's failure instead of the assert's blast radius.
        return {
            "status": "ACTIVE",
            "cash": "1000",
            "equity": "1000",
            "portfolio_value": "1000",
            "buying_power": "2000",
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_open_orders(self) -> list[dict[str, Any]]:
        return list(self._open_orders)


def _worker(
    local_rows: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
) -> tuple[AlpacaPaperWorker, list[Any]]:
    """Build a worker mid-cycle with the per-order step already accounted for.

    Returns the worker and the list of snapshot saves it performs.
    """
    snapshot_writes: list[Any] = []

    # The real executor is built inside __init__; a stub engine plus a stub
    # adapter mean no Postgres, broker or DB write is ever reached.
    worker = AlpacaPaperWorker(
        _ScriptedEngine(local_rows, snapshot_writes),  # type: ignore[arg-type]
        _ScriptedAdapter(open_orders),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )

    # This test is about the account-wide step, so the per-order loop above it
    # is replaced by a no-op. What remains is exactly the ordering under test:
    # validate positions -> assert open orders known -> save snapshot -> open
    # the gate.
    async def _no_active_orders() -> None:
        return None

    worker._reconcile_active_orders = _no_active_orders  # type: ignore[method-assign]

    # `__init__` opens the worker fail-closed. Reproduce the POST-reconcile
    # state explicitly so the assertions below mean what they claim: the assert
    # must LEAVE the gate shut, not merely start from shut.
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None
    worker.has_reconciled = True

    original_save = worker._save_broker_snapshot

    def _recording_save(account, positions, status) -> None:
        snapshot_writes.append((account, positions, status))
        original_save(account, positions, status)

    worker._save_broker_snapshot = _recording_save  # type: ignore[method-assign]
    return worker, snapshot_writes


def _reconcile_once(local_rows: list[dict[str, Any]], open_orders: list[dict[str, Any]]):
    worker, snapshot_writes = _worker(local_rows, open_orders)
    return asyncio.run(worker.reconcile_once()), snapshot_writes


def test_unknown_broker_open_order_aborts_the_whole_cycle():
    """The core guarantee: one unknown live order stops the cycle, whole.

    There is no per-order recovery here even though the sibling
    `_reconcile_active_orders` loop has one. The order is unknown, so we cannot
    say what it is working against the account, and no further reconciliation,
    snapshot or execution may proceed on that basis.
    """
    worker, snapshot_writes = _worker([], [_remote_order(order_id="b-unknown")])

    with pytest.raises(RuntimeError, match="unknown_broker_open_order:b-unknown"):
        asyncio.run(worker.reconcile_once())

    assert snapshot_writes == [], "a diverged book must never be snapshotted"


def test_divergence_leaves_the_execution_gate_shut():
    """Fail CLOSED: the gate must not be opened on an unverified picture.

    `reconcile_once` opens `reconciliation_ready`/`has_reconciled` on its last
    three lines. A raise earlier in the method must leave them False, so the
    next execution decision cannot size an order against this broker state.
    """
    worker, _ = _worker(
        [_local_row(requested_notional=Decimal("100"))],
        [_remote_order(notional="250")],
    )

    with pytest.raises(RuntimeError, match="broker_order_notional_divergence"):
        asyncio.run(worker.reconcile_once())

    assert worker.reconciliation_ready is False
    assert worker.degraded is True


def test_divergence_leaves_no_verified_picture_after_degrading():
    """The raise, followed by the handler `_run` really calls, clears the latch.

    The latch is cleared in TWO places by design, and the split is the point:

    - `reconcile_once` clears only the per-cycle bits (`reconciliation_ready`,
      `degraded`, `degraded_reason` = "reconciliation_in_progress"). It does NOT
      touch `has_reconciled`, the durable counterpart, because a raise is not a
      signal by itself -- `_run` decides what to do with it.
    - `_enter_degraded` is the signal, and it sets `has_reconciled = False`.

    If only the first half existed, the NEXT cycle's in-progress sentinel would
    self-heal a runtime that is failing every single cycle: `health_ready()`
    excuses "reconciliation_in_progress" (worker.py:87), so the window right
    after a raise would read as healthy on the strength of the PREVIOUS
    cycle's verification. The latch is what makes the fault durable, and this
    pins the full path -- raise, then the handler -- rather than half of it.
    """
    worker, _ = _worker(
        [_local_row(requested_notional=Decimal("100"))],
        [_remote_order(notional="250")],
    )

    with pytest.raises(RuntimeError, match="broker_order_notional_divergence"):
        asyncio.run(worker.reconcile_once())

    # Mid-cycle state: fail closed, but still attributed to the in-progress
    # sentinel rather than to a proven fault.
    assert worker.reconciliation_ready is False
    assert worker.degraded is True
    assert worker.degraded_reason == "reconciliation_in_progress"

    # The handler `_run` wraps this in is what makes the fault durable.
    asyncio.run(worker._enter_degraded("broker_order_notional_divergence"))

    assert worker.has_reconciled is False, (
        "a divergent picture must not stay verified across the next cycle"
    )
    assert worker.degraded_reason == "broker_order_notional_divergence"
    assert worker.health_ready() is False


def test_known_order_still_snapshots_and_opens_the_gate():
    """The control: a verified book still completes and is published.

    Without this the tests above would also pass if the assert raised for
    everything, turning the gate permanently shut.
    """
    (account, positions), snapshot_writes = _reconcile_once(
        [_local_row(requested_notional=Decimal("100"))],
        [_remote_order(notional="100")],
    )

    assert account["status"] == "ACTIVE"
    assert positions == []
    assert len(snapshot_writes) == 1, "a verified book must still be snapshotted"


def test_no_open_orders_leaves_nothing_to_verify_and_completes():
    """The normal case: nothing working at the broker needs no verification."""
    _, snapshot_writes = _reconcile_once(
        [_local_row(requested_notional=Decimal("100"))],
        [],
    )

    assert len(snapshot_writes) == 1