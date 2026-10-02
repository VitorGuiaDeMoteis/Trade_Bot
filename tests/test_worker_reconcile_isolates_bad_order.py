"""One unreconcilable order must not degrade the whole worker.

`AlpacaPaperExecutor._required_decimal` raises `RuntimeError("invalid_broker_<field>")`
when a broker numeric cannot be sourced. That fail-closed behaviour is correct
and stays: no fabricated 0 is ever written, and the affected order keeps its
prior status, so it remains in `ACTIVE_ORDER_STATUSES` and is retried on a later
cycle.

What was NOT correct was the blast radius. `_reconcile_active_orders` loops over
every active order calling `reconcile_order` unguarded, so a single malformed
broker payload for ONE order:

1. aborted reconciliation of every remaining order in the batch, leaving their
   fills unrecorded and their in-flight exposure stale; and
2. escaped to `_run`, whose `except Exception` handler calls `_enter_degraded`,
   which releases NO further execution for the rest of the process lifetime.

One order with an unsourceable numeric therefore stopped the entire bot, which
is an availability failure, not a fail-closed one. The fix scopes the fault to
its own order and continues reconciling the rest.

Pure unit test: no Postgres, no broker, no DB mutation. `_reconcile_active_orders`
reads its order ids through `asyncio.to_thread(fetch_active)` and delegates every
write to the executor, so a stub engine plus a scripted executor is enough.
"""

import asyncio
import logging
from decimal import Decimal
from uuid import UUID, uuid5

from services.alpaca_paper.worker import AlpacaPaperWorker

NAMESPACE = UUID("00000000-0000-0000-0000-000000000001")

GOOD_ORDER = uuid5(NAMESPACE, "good")
BAD_ORDER = uuid5(NAMESPACE, "bad")
LATER_ORDER = uuid5(NAMESPACE, "later")


class _RecordingConnection:
    """Minimal connection: `scalars` feeds the active-order ids."""

    def __init__(self, order_ids):
        self.order_ids = list(order_ids)

    def scalars(self, statement):
        return iter(self.order_ids)

    def execute(self, statement, *args, **kwargs):
        return self

    def close(self):
        return None


class _StubEngine:
    def __init__(self, order_ids):
        self.connection = _RecordingConnection(order_ids)

    def connect(self):
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, *exc_info):
        return False


class _ScriptedExecutor:
    """Reconcile each order, failing the ones named in `broken`."""

    def __init__(self, broken):
        self.broken = set(broken)
        self.reconciled: list[UUID] = []

    async def reconcile_order(self, engine, order_id):
        self.reconciled.append(order_id)
        if order_id in self.broken:
            raise RuntimeError("invalid_broker_filled_qty")


def _worker(order_ids, broken) -> tuple[AlpacaPaperWorker, _ScriptedExecutor]:
    # The real executor is built inside __init__; swap it after construction so
    # no adapter, DB or broker is ever touched.
    worker = AlpacaPaperWorker(_StubEngine(order_ids), None, None)
    executor = _ScriptedExecutor(broken)
    worker.executor = executor
    # `__init__` opens the worker fail-closed (`degraded=True`,
    # `reconciliation_ready=False`, reason "startup_reconciliation_pending").
    # `reconcile_once` is the only thing that clears that, and it needs the
    # adapter/DB this test deliberately avoids. Reproduce the POST-reconcile
    # state explicitly, so the assertions below mean what they claim: the loop
    # under test must LEAVE the gate it was given, not resurrect it.
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None
    worker.has_reconciled = True
    return worker, executor


def _reconcile(order_ids, broken):
    worker, executor = _worker(order_ids, broken)
    asyncio.run(worker._reconcile_active_orders())
    return worker, executor


def test_bad_order_in_middle_does_not_stop_later_orders():
    """The core regression: a fault on one order must not abort the batch."""
    worker, executor = _reconcile([GOOD_ORDER, BAD_ORDER, LATER_ORDER], [BAD_ORDER])

    assert executor.reconciled == [GOOD_ORDER, BAD_ORDER, LATER_ORDER]
    assert worker.degraded is False
    assert worker.reconciliation_ready is True


def test_batch_of_mixed_orders_raises_nothing():
    """The loop must not propagate: `_run` degrades on any escape."""
    worker, _ = _reconcile([GOOD_ORDER, BAD_ORDER], [BAD_ORDER])

    # `reconcile_once` owns `degraded`/`reconciliation_ready`; the loop must not
    # touch either, because only a genuine whole-cycle failure may degrade.
    assert worker.degraded is False


def test_single_bad_order_is_isolated_and_retried_next_cycle():
    """The bad order stays in ACTIVE_ORDER_STATUSES, so the next cycle retries it.

    Reconciliation is skipped, never marked terminal: the row keeps its prior
    status, so `fetch_active` still returns it and the loop below sees it again.
    """
    _, first = _reconcile([BAD_ORDER], [BAD_ORDER])
    assert first.reconciled == [BAD_ORDER]

    # A later cycle with the broker payload repaired reconciles it normally.
    _, second = _reconcile([BAD_ORDER], [])
    assert second.reconciled == [BAD_ORDER]


def test_all_orders_fine_still_reconciles_every_order():
    _, executor = _reconcile([GOOD_ORDER, LATER_ORDER], [])

    assert executor.reconciled == [GOOD_ORDER, LATER_ORDER]


def test_deferred_order_is_logged_as_a_warning(caplog):
    """An operator must be able to SEE which order was deferred and why."""
    with caplog.at_level(logging.WARNING, logger="trading_bot.alpaca_worker"):
        _reconcile([BAD_ORDER], [BAD_ORDER])

    messages = [record.getMessage() for record in caplog.records]
    assert any(str(BAD_ORDER) in message for message in messages)
    assert any("invalid_broker_filled_qty" in message for message in messages)


def test_empty_batch_is_a_noop():
    worker, executor = _reconcile([], [GOOD_ORDER])

    assert executor.reconciled == []
    assert worker.degraded is False


def test_decimal_helper_still_fails_closed_on_unsourceable_value():
    """The per-order fail-closed contract the loop relies on is unchanged."""
    from services.alpaca_paper.executor import AlpacaPaperExecutor

    assert AlpacaPaperExecutor._required_decimal({"filled_qty": "2.5"}, "filled_qty") == Decimal(
        "2.5"
    )

    import pytest

    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({}, "filled_qty")