"""Worker BUY sizing: notional-only orders, never a share quantity.

`_process_pending_submits` is the ONLY place that turns an APPROVED risk
decision into a broker order, and it treats the two sides asymmetrically:

- SELL computes a share quantity (`broker_quantity - pending_sell_quantity`);
  that arithmetic is covered by tests/test_worker_pending_sell_sizing.py.
- BUY sends NO share quantity at all: it hands `quantity = Decimal("0")` and
  `notional = ExecutionGuard.MAX_NOTIONAL_PER_TRADE` to the executor
  (worker.py:424-426), i.e. a dollar order.

The two sides share one guard call and one submit call, so a mistake in the BUY
branch is invisible to the SELL tests. Two failure modes are financially
material:

- a BUY that carries a share quantity instead of a notional sends an order of
  the WRONG SIZE (or an invalid one) for a dollar-denominated decision;
- the guard RESERVES `MAX_NOTIONAL_PER_TRADE` when it charges the new BUY
  against `MAX_TOTAL_EXPOSURE` (guard.py:160-168). If the worker submitted a
  different notional than the guard reserved, the total-exposure cap would be
  enforced against a number that no order actually used.

So the tests below assert against `ExecutionGuard.MAX_NOTIONAL_PER_TRADE` itself
rather than a hardcoded 10.00: changing the constant in one place only fails
these tests, which is exactly the regression worth catching.

Engine is stubbed with a scripted connection (no Postgres, no broker, no DB
mutation) and the executor is replaced by a recorder, so the exact kwargs handed
to `submit` are observable. `ExecutionGuard.evaluate` runs for real, so the
"nothing was submitted" assertions prove the guard's BUY branch short-circuited.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from services.alpaca_paper.guard import ExecutionGuard
from services.alpaca_paper.worker import AlpacaPaperWorker

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
DECISION_ID = UUID("22222222-2222-2222-2222-222222222222")
SIGNAL_ID = UUID("33333333-3333-3333-3333-333333333333")

MAX_NOTIONAL = ExecutionGuard.MAX_NOTIONAL_PER_TRADE
MAX_EXPOSURE = ExecutionGuard.MAX_TOTAL_EXPOSURE


def _account(**overrides: Any) -> dict[str, Any]:
    account = {
        "status": "ACTIVE",
        "cash": "1000",
        "equity": "1000",
        "portfolio_value": "1000",
        "last_equity": "1000",
    }
    account.update(overrides)
    return account


def _position(symbol: str = "AAPL", qty: str = "10", market_value: str = "150") -> dict[str, Any]:
    return {"symbol": symbol, "qty": qty, "market_value": market_value}


def _pending_row(side: str = "BUY", symbol: str = "AAPL") -> dict[str, Any]:
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


def _in_flight(
    symbol: str, side: str, quantity: str | None = None, notional: str | None = None
) -> dict[str, Any]:
    """One row of the in-flight join: paper_orders + broker_orders columns."""
    return {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "requested_notional": notional,
    }


class _ScriptedResult:
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
        return _ScriptedResult(self._engine.next_execute_rows())

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
) -> tuple[AlpacaPaperWorker, _ScriptedEngine, _RecordingExecutor]:
    engine = _ScriptedEngine(pending=pending, in_flight=in_flight)
    worker = AlpacaPaperWorker(engine, None, None)  # type: ignore[arg-type]
    worker.degraded = False
    worker.reconciliation_ready = True
    executor = _RecordingExecutor()
    worker.executor = executor  # type: ignore[assignment]
    return worker, engine, executor


def _run(
    worker: AlpacaPaperWorker,
    account: dict[str, Any] | None = None,
    positions: list[dict[str, Any]] | None = None,
) -> None:
    asyncio.run(
        worker._process_pending_submits(
            account=_account() if account is None else account,
            positions=[] if positions is None else positions,
        )
    )


def _rejection_reasons(engine: _ScriptedEngine) -> list[str]:
    reasons = []
    for _, statement in engine.executed:
        if statement.__class__.__name__ != "Update":
            continue
        params = statement.compile().params
        if "reason" in params:
            reasons.append(str(params["reason"]))
    return reasons


def test_buy_submits_the_max_notional_and_no_share_quantity() -> None:
    worker, _, executor = _worker()

    _run(worker)

    assert len(executor.submissions) == 1
    submission = executor.submissions[0]
    assert submission["side"] == "BUY"
    assert submission["symbol"] == "AAPL"
    assert submission["quantity"] == Decimal("0")
    assert submission["notional"] == MAX_NOTIONAL


def test_buy_notional_is_exactly_what_the_guard_reserved_against_exposure() -> None:
    """Guard charges MAX_NOTIONAL to the cap; the order must use that amount.

    If the worker sent a different notional, `MAX_TOTAL_EXPOSURE` would be
    enforced against a figure no order ever used.
    """
    worker, _, executor = _worker()

    _run(worker)

    submitted = executor.submissions[0]["notional"]
    assert submitted == ExecutionGuard.MAX_NOTIONAL_PER_TRADE


def test_buy_is_approved_with_a_flat_account_and_no_open_positions() -> None:
    worker, engine, executor = _worker()

    _run(worker)

    assert len(executor.submissions) == 1
    assert _rejection_reasons(engine) == []


def test_buy_exposure_exactly_at_the_cap_is_still_approved() -> None:
    """total_exposure + in_flight + MAX_NOTIONAL == MAX_TOTAL_EXPOSURE passes."""
    worker, _, executor = _worker()
    positions = [_position("SPY", qty="1", market_value=str(MAX_EXPOSURE - MAX_NOTIONAL))]

    _run(worker, positions=positions)

    assert len(executor.submissions) == 1


def test_buy_one_cent_over_the_exposure_cap_is_rejected() -> None:
    worker, engine, executor = _worker()
    over = MAX_EXPOSURE - MAX_NOTIONAL + Decimal("0.01")
    positions = [_position("SPY", qty="1", market_value=str(over))]

    _run(worker, positions=positions)

    assert executor.submissions == []
    assert any("Exposição máxima total" in reason for reason in _rejection_reasons(engine))


def test_in_flight_buy_notional_counts_toward_the_exposure_cap() -> None:
    worker, engine, executor = _worker(
        in_flight=[_in_flight("SPY", "BUY", notional=str(MAX_EXPOSURE - MAX_NOTIONAL))]
    )

    _run(worker)

    assert len(executor.submissions) == 1

    over_cap = _worker(in_flight=[_in_flight("SPY", "BUY", notional="21.00")])
    _run(over_cap[0])

    assert over_cap[2].submissions == []
    assert any(
        "incluindo in-flight" in reason for reason in _rejection_reasons(over_cap[1])
    )


def test_buy_with_unsourceable_in_flight_notional_fails_closed() -> None:
    worker, engine, executor = _worker(in_flight=[_in_flight("SPY", "BUY", notional=None)])

    _run(worker)

    assert executor.submissions == []
    assert any("in-flight desconhecida" in reason for reason in _rejection_reasons(engine))


def test_buy_with_an_open_position_for_the_symbol_is_rejected_no_pyramiding() -> None:
    worker, engine, executor = _worker()

    _run(worker, positions=[_position("AAPL", qty="2", market_value="300")])

    assert executor.submissions == []
    assert any("no pyramiding" in reason for reason in _rejection_reasons(engine))


def test_buy_with_a_pending_buy_in_flight_is_rejected_no_pyramiding() -> None:
    worker, engine, executor = _worker(in_flight=[_in_flight("AAPL", "BUY", notional="10.00")])

    _run(worker)

    assert executor.submissions == []
    assert any("no pyramiding" in reason for reason in _rejection_reasons(engine))


def test_buy_with_unsourceable_market_value_on_another_position_fails_closed() -> None:
    worker, engine, executor = _worker()
    positions = [{"symbol": "SPY", "qty": "3", "market_value": None}]

    _run(worker, positions=positions)

    assert executor.submissions == []
    assert any("Exposição da posição" in reason for reason in _rejection_reasons(engine))


def test_buy_with_unsourceable_qty_on_another_position_fails_closed() -> None:
    worker, engine, executor = _worker()
    positions = [{"symbol": "SPY", "qty": None, "market_value": "12.00"}]

    _run(worker, positions=positions)

    assert executor.submissions == []
    assert any(
        "indisponível para o cálculo de exposição" in reason
        for reason in _rejection_reasons(engine)
    )


def test_buy_without_last_equity_baseline_fails_closed() -> None:
    worker, engine, executor = _worker()
    account = _account()
    account.pop("last_equity")

    _run(worker, account=account)

    assert executor.submissions == []
    assert any("baseline last_equity" in reason for reason in _rejection_reasons(engine))


def test_buy_trips_the_daily_breaker_when_the_loss_reaches_the_limit() -> None:
    worker, engine, executor = _worker()

    _run(worker, account=_account(last_equity="1000", equity="995"))

    assert executor.submissions == []
    assert any("Circuit breaker diário" in reason for reason in _rejection_reasons(engine))


def test_sell_still_submits_when_the_buy_side_data_is_unavailable() -> None:
    """Fail-closed is BUY-only: a missing baseline must not block flattening."""
    worker, _, executor = _worker(pending=[_pending_row(side="SELL", symbol="AAPL")])
    account = _account()
    account.pop("last_equity")

    _run(worker, account=account, positions=[_position("AAPL", qty="10")])

    assert len(executor.submissions) == 1
    assert executor.submissions[0]["side"] == "SELL"
    assert executor.submissions[0]["quantity"] == Decimal("10")
    assert executor.submissions[0]["notional"] is None


def test_buy_of_a_symbol_outside_the_v1_allowlist_is_rejected() -> None:
    symbol = "NVDA"
    assert symbol not in ExecutionGuard.ALLOWED_SYMBOLS
    worker, engine, executor = _worker(pending=[_pending_row(side="BUY", symbol=symbol)])

    _run(worker)

    assert executor.submissions == []
    assert any("não permitido na V1" in reason for reason in _rejection_reasons(engine))