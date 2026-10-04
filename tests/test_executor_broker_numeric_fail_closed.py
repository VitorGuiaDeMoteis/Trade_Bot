"""
Executor must FAIL CLOSED on broker numerics it is required to persist.

Bug class: `dict.get(key, "0")` fabricates a 0 when a REQUIRED broker numeric is
absent OR explicitly None. In `reconcile_order` a fabricated filled_qty of 0 is
worse than cosmetic: it skips the whole `if filled_qty > 0` block, so real fills
are NEVER persisted and the local ledger silently under-reports execution.

Pure unit tests (no DB, no broker, no HTTP): adapter and engine are stubbed so we
can assert the executor RAISES instead of inventing a numeric, and that it writes
nothing on that path.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from services.alpaca_paper.executor import AlpacaPaperExecutor


class _StubAdapter:
    """Minimal AlpacaPaperAdapter stand-in driven by scripted payloads."""

    def __init__(
        self,
        by_id: dict[str, Any] | None = None,
        by_client_id: dict[str, Any] | None = None,
        fills: list[dict[str, Any]] | None = None,
    ) -> None:
        self._by_id = by_id
        self._by_client_id = by_client_id
        self._fills = fills or []

    async def get_order_by_id(self, broker_order_id: str) -> dict[str, Any] | None:
        return self._by_id

    async def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any] | None:
        return self._by_client_id

    async def get_fills(self, broker_order_id: str) -> list[dict[str, Any]]:
        return self._fills

    async def submit_order(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("submit_order must not be called")


class _Row:
    def __init__(self, broker_order_id: str | None, client_order_id: str) -> None:
        self.broker_order_id = broker_order_id
        self.client_order_id = client_order_id


class _StubConnection:
    def __init__(self, row: _Row | None, sink: list[Any]) -> None:
        self._row = row
        self._sink = sink

    def execute(self, statement: Any) -> "_StubConnection":
        self._sink.append(statement)
        return self

    def first(self) -> _Row | None:
        return self._row


class _StubEngine:
    """Records every executed statement so tests can assert nothing was written."""

    def __init__(self, broker_order_id: str | None = "B-1") -> None:
        self.statements: list[Any] = []
        self._row = _Row(broker_order_id, "m7_abc")

    def begin(self) -> Any:
        engine = self

        class _Ctx:
            def __enter__(self) -> _StubConnection:
                return _StubConnection(engine._row, engine.statements)

            def __exit__(self, *exc: object) -> bool:
                return False

        return _Ctx()

    @property
    def touched_tables(self) -> set[str]:
        tables: set[str] = set()
        for statement in self.statements:
            table = getattr(statement, "table", None)
            if table is not None:
                tables.add(table.name)
        return tables


# ---------------------------------------------------------------------------
# _required_decimal: the core guard
# ---------------------------------------------------------------------------


def test_required_decimal_rejects_missing_key() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({}, "filled_qty")


def test_required_decimal_rejects_explicit_none() -> None:
    # The exact .get(key, "0") trap: key PRESENT but None returns None, so the
    # default never applies and Decimal("None") raises InvalidOperation.
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({"filled_qty": None}, "filled_qty")


def test_required_decimal_rejects_empty_string() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({"filled_qty": ""}, "filled_qty")


def test_required_decimal_rejects_garbage_text() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({"filled_qty": "not-a-number"}, "filled_qty")


def test_required_decimal_rejects_non_finite() -> None:
    # Decimal("NaN") parses cleanly but poisons every downstream comparison.
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({"filled_qty": "NaN"}, "filled_qty")
    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        AlpacaPaperExecutor._required_decimal({"filled_qty": "Infinity"}, "filled_qty")


def test_required_decimal_accepts_valid_string_number_and_zero() -> None:
    parse = AlpacaPaperExecutor._required_decimal
    assert parse({"filled_qty": "3"}, "filled_qty") == Decimal(3)
    assert parse({"filled_qty": 3.5}, "filled_qty") == Decimal("3.5")
    assert parse({"filled_qty": "0"}, "filled_qty") == Decimal(0)


def test_required_decimal_uses_custom_field_label() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_fill_price"):
        AlpacaPaperExecutor._required_decimal({"price": None}, "price", "fill_price")
    with pytest.raises(RuntimeError, match="invalid_broker_fill_quantity"):
        AlpacaPaperExecutor._required_decimal({}, "qty", "fill_quantity")


# ---------------------------------------------------------------------------
# reconcile_order: no fabricated 0, no silently skipped fills
# ---------------------------------------------------------------------------


def test_reconcile_order_raises_when_filled_qty_missing() -> None:
    executor = AlpacaPaperExecutor(
        _StubAdapter(by_id={"id": "B-1", "status": "partially_filled"})
    )

    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        asyncio.run(executor.reconcile_order(_StubEngine(), uuid4()))  # type: ignore[arg-type]


def test_reconcile_order_raises_when_filled_qty_none() -> None:
    executor = AlpacaPaperExecutor(
        _StubAdapter(by_id={"id": "B-1", "status": "filled", "filled_qty": None})
    )

    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        asyncio.run(executor.reconcile_order(_StubEngine(), uuid4()))  # type: ignore[arg-type]


def test_reconcile_order_writes_nothing_when_numeric_unsourceable() -> None:
    """A payload we cannot trust must not partially persist order status."""
    executor = AlpacaPaperExecutor(
        _StubAdapter(by_id={"id": "B-1", "status": "filled", "filled_qty": None})
    )
    engine = _StubEngine()

    with pytest.raises(RuntimeError, match="invalid_broker_filled_qty"):
        asyncio.run(executor.reconcile_order(engine, uuid4()))  # type: ignore[arg-type]

    # No UPDATE may have landed on either orders table.
    assert engine.touched_tables == set()


def test_reconcile_order_never_persists_zero_price_fill() -> None:
    """Each fill's own numerics fail closed too: no broker_fills row with 0."""
    executor = AlpacaPaperExecutor(
        _StubAdapter(
            by_id={"id": "B-1", "status": "filled", "filled_qty": "2"},
            fills=[{"id": "F-1", "qty": "1", "price": None}],
        )
    )
    engine = _StubEngine()

    with pytest.raises(RuntimeError, match="invalid_broker_fill_price"):
        asyncio.run(executor.reconcile_order(engine, uuid4()))  # type: ignore[arg-type]

    assert "broker_fills" not in engine.touched_tables


# ---------------------------------------------------------------------------
# _required_timestamp: a fill's WHEN is never invented
# ---------------------------------------------------------------------------


def test_required_timestamp_rejects_missing_key() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp({}, "transaction_time", "fill_time")


def test_required_timestamp_rejects_explicit_none() -> None:
    # Key PRESENT but None: a truthiness guard (`if t_time:`) treats this the same
    # as absent and reaches for now() - the exact trap this closes.
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp(
            {"transaction_time": None}, "transaction_time", "fill_time"
        )


def test_required_timestamp_rejects_empty_and_garbage() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp(
            {"transaction_time": ""}, "transaction_time", "fill_time"
        )
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp(
            {"transaction_time": "not-a-timestamp"}, "transaction_time", "fill_time"
        )


def test_required_timestamp_rejects_non_string() -> None:
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp(
            {"transaction_time": 1757000000}, "transaction_time", "fill_time"
        )


def test_required_timestamp_rejects_naive_datetime() -> None:
    # A naive time bound for a timestamptz column is read in the SERVER's zone:
    # accepted, but silently shifted. Fail closed instead.
    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        AlpacaPaperExecutor._required_timestamp(
            {"transaction_time": "2026-10-04T12:00:00"}, "transaction_time", "fill_time"
        )


def test_required_timestamp_accepts_utc_and_offset_forms() -> None:
    parse = AlpacaPaperExecutor._required_timestamp
    assert parse(
        {"transaction_time": "2026-10-04T12:00:00Z"}, "transaction_time", "fill_time"
    ) == datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert parse(
        {"transaction_time": "2026-10-04T09:00:00-03:00"}, "transaction_time", "fill_time"
    ) == datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _executor_with_fill(fill: dict[str, Any]) -> AlpacaPaperExecutor:  # type: ignore[arg-type]
    return AlpacaPaperExecutor(
        _StubAdapter(
            by_id={"id": "B-1", "status": "filled", "filled_qty": "1"},
            fills=[fill],
        )
    )


def test_reconcile_order_raises_when_fill_time_missing() -> None:
    executor = _executor_with_fill(
        {"id": "F-1", "qty": "1", "price": "10", "transaction_time": None}
    )
    engine = _StubEngine()

    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        asyncio.run(executor.reconcile_order(engine, uuid4()))  # type: ignore[arg-type]

    # The unsourceable fill must not be persisted with a fabricated "now".
    assert "broker_fills" not in engine.touched_tables


def test_reconcile_order_raises_when_fill_time_garbled() -> None:
    executor = _executor_with_fill(
        {"id": "F-1", "qty": "1", "price": "10", "transaction_time": "yesterday-ish"}
    )

    with pytest.raises(RuntimeError, match="invalid_broker_fill_time"):
        asyncio.run(executor.reconcile_order(_StubEngine(), uuid4()))  # type: ignore[arg-type]


def test_reconcile_order_still_accepts_a_good_fill_time() -> None:
    """Guard against over-rejecting: the valid path must keep working."""
    executor = _executor_with_fill(
        {
            "id": "F-1",
            "qty": "1",
            "price": "10",
            "transaction_time": "2026-10-04T12:00:00Z",
        }
    )
    engine = _StubEngine()

    asyncio.run(executor.reconcile_order(engine, uuid4()))  # type: ignore[arg-type]

    assert "broker_fills" in engine.touched_tables