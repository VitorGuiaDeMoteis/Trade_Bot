"""Worker SELL sizing: `broker_quantity - pending_sell_quantity`.

`AlpacaPaperWorker._process_pending_submits` is the ONLY place that decides how
many shares a position-closing SELL may send, and it is a trading decision made
from two independently sourced numbers:

- `broker_quantity`: the live broker position qty for the traded symbol;
- `pending_sell_quantity`: the qty already committed by in-flight SELL orders.

Getting this arithmetic wrong is a financial-safety bug in both directions: too
large and the bot oversells into a short position, too small and it leaves dust
behind. `tests/test_alpaca_worker.py` covers this method only through
DB-backed tests that cannot run without Postgres, so the arithmetic itself had
NO pure unit coverage.

The engine is stubbed with a scripted connection (no Postgres, no broker, no DB
mutation) and the executor is replaced by a recorder, so the exact quantity
handed to `submit` is observable. `ExecutionGuard.evaluate` runs for real, which
is what makes these tests meaningful: it proves the guard's own rejection paths
still short-circuit before any submit.
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from services.alpaca_paper.worker import AlpacaPaperWorker

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
DECISION_ID = UUID("22222222-2222-2222-2222-222222222222")
SIGNAL_ID = UUID("33333333-3333-3333-3333-333333333333")

ACCOUNT = {
    "status": "ACTIVE",
    "cash": "100",
    "equity": "1000",
    "portfolio_value": "1000",
    "last_equity": "1000",
}


def _position(symbol: str = "AAPL", qty: str = "10", market_value: str = "150") -> dict[str, Any]:
    return {"symbol": symbol, "qty": qty, "market_value": market_value}


def _pending_row(side: str = "SELL", symbol: str = "AAPL") -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "decision_id": DECISION_ID,
        "signal_id": SIGNAL_ID,
        "decision": "APPROVED",
        "reason": "ok",
        "decided_at": datetime.now(UTC),
        "symbol": symbol,
        "signal_type": side,
    }


class _ScriptedResult:
    """Result object supporting the SQLAlchemy calls the worker actually makes."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> "_ScriptedResult":
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _ScriptedConnection:
    def __init__(self, engine: "_ScriptedEngine", mode: str) -> None:
        self._engine = engine
        self._mode = mode

    def execute(self, statement, *args, **kwargs):
        self._engine.executed.append((self._mode, statement))
        rows = self._engine.next_execute_rows()
        return _ScriptedResult(rows)

    def scalars(self, statement, *args, **kwargs):
        self._engine.executed.append((self._mode, statement))
        return list(self._engine.blocked_symbols)

    def __enter__(self) -> "_ScriptedConnection":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class _ScriptedEngine:
    """Feeds canned rows in call order: controls, pending, then in-flight."""

    def __init__(
        self,
        pending: list[dict[str, Any]] | None = None,
        in_flight: list[dict[str, Any]] | None = None,
        blocked_symbols: list[str] | None = None,
    ) -> None:
        self._queue: list[list[Any]] = [
            [{"paused": False, "active_run_id": RUN_ID}],
            list(pending if pending is not None else [_pending_row()]),
            list(in_flight or []),
        ]
        self.blocked_symbols = list(blocked_symbols or [])
        self.executed: list[tuple[str, Any]] = []

    def next_execute_rows(self) -> list[Any]:
        return self._queue.pop(0) if self._queue else []

    def connect(self) -> _ScriptedConnection:
        return _ScriptedConnection(self, "connect")

    def begin(self) -> _ScriptedConnection:
        return _ScriptedConnection(self, "begin")


class _RecordingExecutor:
    def __init__(self) -> None:
        self.submissions: list[dict[str, Any]] = []

    async def submit(self, **kwargs: Any) -> None:
        self.submissions.append(kwargs)


def _worker(
    *,
    pending: list[dict[str, Any]] | None = None,
    in_flight: list[dict[str, Any]] | None = None,
    blocked_symbols: list[str] | None = None,
) -> tuple[AlpacaPaperWorker, _ScriptedEngine, _RecordingExecutor]:
    engine = _ScriptedEngine(
        pending=pending, in_flight=in_flight, blocked_symbols=blocked_symbols
    )
    worker = AlpacaPaperWorker(engine, None, None)  # type: ignore[arg-type]
    worker.degraded = False
    worker.reconciliation_ready = True
    executor = _RecordingExecutor()
    worker.executor = executor  # type: ignore[assignment]
    return worker, engine, executor


def _run(worker: AlpacaPaperWorker, positions: list[dict[str, Any]]) -> None:
    asyncio.run(worker._process_pending_submits(account=ACCOUNT, positions=positions))


def _submitted_quantities(executor: _RecordingExecutor) -> list[Decimal]:
    return [submission["quantity"] for submission in executor.submissions]


def _rejection_reasons(engine: _ScriptedEngine) -> list[str]:
    """Reasons written back to risk_decisions by the guard's rejection branch."""
    reasons = []
    for _, statement in engine.executed:
        if statement.__class__.__name__ != "Update":
            continue
        params = statement.compile().params
        if "reason" in params:
            reasons.append(str(params["reason"]))
    return reasons


def test_sell_submits_full_position_when_nothing_is_in_flight():
    worker, _, executor = _worker()

    _run(worker, [_position(qty="10")])

    assert _submitted_quantities(executor) == [Decimal("10")]


def test_sell_subtracts_pending_sell_quantity():
    """The core arithmetic: 10 held, 4 already committed -> sell 6."""
    worker, _, executor = _worker(
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": Decimal("4")}]
    )

    _run(worker, [_position(qty="10")])

    assert _submitted_quantities(executor) == [Decimal("6")]


def test_sell_subtracts_every_pending_sell_not_just_the_first():
    worker, _, executor = _worker(
        in_flight=[
            {"symbol": "AAPL", "side": "SELL", "quantity": Decimal("3")},
            {"symbol": "AAPL", "side": "SELL", "quantity": Decimal("2.5")},
        ]
    )

    _run(worker, [_position(qty="10")])

    assert _submitted_quantities(executor) == [Decimal("4.5")]


def test_pending_sell_of_another_symbol_is_not_subtracted():
    worker, _, executor = _worker(
        in_flight=[{"symbol": "TSLA", "side": "SELL", "quantity": Decimal("4")}]
    )

    _run(worker, [_position("AAPL", qty="10"), _position("TSLA", qty="5")])

    assert _submitted_quantities(executor) == [Decimal("10")]


def test_pending_buy_does_not_reduce_a_sell():
    worker, _, executor = _worker(
        in_flight=[
            {"symbol": "AAPL", "side": "BUY", "quantity": None, "requested_notional": Decimal("10")}
        ]
    )

    _run(worker, [_position(qty="10")])

    assert _submitted_quantities(executor) == [Decimal("10")]


def test_pending_sell_covering_the_whole_position_is_rejected_not_oversold():
    """Guard blocks it first; the worker must not submit a zero/negative qty."""
    worker, engine, executor = _worker(
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": Decimal("10")}]
    )

    _run(worker, [_position(qty="10")])

    assert executor.submissions == []
    assert any("a descoberto" in reason for reason in _rejection_reasons(engine))


def test_pending_sell_larger_than_the_position_is_rejected():
    worker, engine, executor = _worker(
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": Decimal("25")}]
    )

    _run(worker, [_position(qty="10")])

    assert executor.submissions == []
    assert _rejection_reasons(engine)


def test_pending_sell_with_unsourceable_quantity_never_reaches_submission():
    """A NULL in-flight SELL qty must fail closed, not be read as zero sold."""
    worker, engine, executor = _worker(
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": None}]
    )

    _run(worker, [_position(qty="10")])

    assert executor.submissions == []
    assert any("in-flight desconhecida" in reason for reason in _rejection_reasons(engine))


def test_sell_without_a_position_is_rejected():
    worker, engine, executor = _worker()

    _run(worker, [_position("TSLA", qty="5")])

    assert executor.submissions == []
    assert _rejection_reasons(engine)


def test_position_with_unsourceable_quantity_is_rejected():
    """No fabricated qty: the guard rejects before the worker sums positions."""
    worker, engine, executor = _worker()

    _run(worker, [{"symbol": "AAPL", "market_value": "150"}])

    assert executor.submissions == []
    assert any("Quantidade da posição" in reason for reason in _rejection_reasons(engine))


def test_sell_submit_carries_no_notional():
    """SELLs are share-quantity orders; a notional would be a different order."""
    worker, _, executor = _worker()

    _run(worker, [_position(qty="10")])

    assert executor.submissions[0]["notional"] is None
    assert executor.submissions[0]["side"] == "SELL"
    assert executor.submissions[0]["symbol"] == "AAPL"


def test_degraded_worker_submits_nothing():
    worker, engine, executor = _worker()
    worker.degraded = True

    _run(worker, [_position(qty="10")])

    assert executor.submissions == []
    assert engine.executed == []


def test_paused_control_returns_without_querying_pending_rows(
    caplog: pytest.LogCaptureFixture,
):
    """A paused system must not trade, and must not log a broker error."""
    engine = _ScriptedEngine()
    engine._queue[0] = [{"paused": True, "active_run_id": RUN_ID}]
    worker = AlpacaPaperWorker(engine, None, None)  # type: ignore[arg-type]
    worker.degraded = False
    worker.reconciliation_ready = True
    executor = _RecordingExecutor()
    worker.executor = executor  # type: ignore[assignment]

    with caplog.at_level(logging.ERROR):
        _run(worker, [_position(qty="10")])

    assert executor.submissions == []
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
