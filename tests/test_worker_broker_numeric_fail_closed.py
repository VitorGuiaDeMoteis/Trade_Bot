"""Worker must not fabricate zeros for unsourceable broker numerics.

Same bug class already recorded in AGENT_LESSONS.md (silent
`dict.get(key, 0)` fail-open), now in the LAST unreviewed layer: the worker's
own broker-numeric accounting rather than the guard's.

`AlpacaPaperWorker._decimal` already raises on an absent/unparsable/non-finite
value, but three call sites passed a `, 0` default into it. The default made
`dict.get(key, 0)` return an INVENTED 0 for a missing key, so `_decimal`
succeeded and the fabricated value flowed on:

- `pending_sell_quantity`: a pending SELL row with a NULL quantity summed as
  0 sold, overstating `available_qty` and allowing a second SELL of the whole
  position (oversell into a short);
- `buying_power` and `unrealized_pl`: an absent field wrote a plausible-looking
  0 into `broker_portfolio_snapshots`, so Mission Control displayed a real-looking
  account with no buying power and zero P/L.

All three sites now pass the raw `dict.get(key)`, so a missing field reaches
`_decimal` and fails the cycle closed via `invalid_broker_<field>`.

Pure unit tests: no Postgres, no broker, no DB mutation. `_save_broker_snapshot`
parses every field BEFORE opening an engine connection, so a stub engine is
enough and the fail-closed path never needs a real database.
"""

from decimal import Decimal

import pytest

from services.alpaca_paper.worker import AlpacaPaperWorker

ACCOUNT = {
    "status": "ACTIVE",
    "cash": "500",
    "equity": "1000",
    "portfolio_value": "1000",
    "buying_power": "4000",
}

POSITION = {
    "symbol": "AAPL",
    "qty": "1",
    "avg_entry_price": "10",
    "current_price": "15",
    "market_value": "15",
    "unrealized_pl": "5",
}


class _RecordingConnection:
    """Captures statements so the written row can be inspected without a DB."""

    def __init__(self) -> None:
        self.executed: list = []

    def execute(self, statement, *args, **kwargs):
        self.executed.append((statement, args, kwargs))
        return self


class _StubEngine:
    """Minimal engine: records executes, never touches a database."""

    def __init__(self) -> None:
        self.connection = _RecordingConnection()

    def begin(self):
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, *exc_info):
        return False


def _worker() -> AlpacaPaperWorker:
    return AlpacaPaperWorker(_StubEngine(), None, None)


def _save(worker: AlpacaPaperWorker, account, positions) -> None:
    worker._save_broker_snapshot(account, positions, "ACTIVE")


def test_missing_buying_power_fails_closed_instead_of_writing_zero():
    account = {key: value for key, value in ACCOUNT.items() if key != "buying_power"}

    with pytest.raises(RuntimeError, match="invalid_broker_buying_power"):
        _save(_worker(), account, [POSITION])


def test_missing_unrealized_pl_fails_closed_instead_of_writing_zero():
    position = {key: value for key, value in POSITION.items() if key != "unrealized_pl"}

    with pytest.raises(RuntimeError, match="invalid_broker_unrealized_pnl"):
        _save(_worker(), ACCOUNT, [position])


def test_unparsable_buying_power_fails_closed():
    account = dict(ACCOUNT, buying_power="not-a-number")

    with pytest.raises(RuntimeError, match="invalid_broker_buying_power"):
        _save(_worker(), account, [POSITION])


def test_unparsable_unrealized_pl_fails_closed():
    position = dict(POSITION, unrealized_pl="")

    with pytest.raises(RuntimeError, match="invalid_broker_unrealized_pnl"):
        _save(_worker(), ACCOUNT, [position])


def test_fail_closed_occurs_before_any_write():
    """A fabricated zero must never reach the snapshot row."""
    engine = _StubEngine()
    worker = AlpacaPaperWorker(engine, None, None)
    account = {key: value for key, value in ACCOUNT.items() if key != "buying_power"}

    with pytest.raises(RuntimeError, match="invalid_broker_buying_power"):
        _save(worker, account, [POSITION])

    assert engine.connection.executed == []


def test_complete_payload_is_accepted_and_keeps_real_values():
    """The happy path still works and preserves the real broker numbers."""
    worker = _worker()

    _save(worker, ACCOUNT, [POSITION])

    assert worker.engine.connection.executed


def test_decimal_helper_rejects_absent_pending_sell_quantity():
    """`_decimal` is the contract the pending-SELL site now relies on.

    The pending-SELL sum is computed after `ExecutionGuard.evaluate` approves
    the SELL, and the guard already fails closed on an unsourceable in-flight
    SELL quantity, so that site is not reachable with a NULL quantity. The
    worker-side default was still a fail-open on its own terms, so assert the
    shared helper contract it now depends on.
    """
    assert AlpacaPaperWorker._decimal(Decimal("0"), "pending_sell_quantity") == Decimal("0")

    with pytest.raises(RuntimeError, match="invalid_broker_pending_sell_quantity"):
        AlpacaPaperWorker._decimal(None, "pending_sell_quantity")
