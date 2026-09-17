import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError

from scripts import paper_ops
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.guard import ExecutionGuard
from services.alpaca_paper.worker import AlpacaPaperWorker
from services.api.config import Settings
from services.api.database import create_database_engine, get_alembic_head, get_alembic_heads


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_test_mode_runtime_database_refused_before_engine_creation(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_role="test",
        postgres_db="trading_bot_test",
    )
    unsafe = settings.model_copy(update={"postgres_db": "trading_bot_dev"})
    create = MagicMock()
    monkeypatch.setattr("services.api.database.create_engine", create)

    with pytest.raises(ValueError, match="REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE"):
        create_database_engine(unsafe)

    create.assert_not_called()


def test_explicit_test_database_is_allowed():
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_role="test",
        postgres_db="trading_bot_test",
    )
    assert settings.database_url.database == "trading_bot_test"


def test_runtime_mode_test_database_is_refused():
    with pytest.raises(ValidationError, match="runtime cannot connect to test database"):
        Settings(
            _env_file=None,
            app_env="local",
            database_role="runtime",
            postgres_db="trading_bot_test",
        )


@pytest.mark.anyio
async def test_start_preflight_refuses_database_revision_behind_head(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(paper_ops, "runtime_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(paper_ops, "get_alembic_heads", lambda: ("head",))
    monkeypatch.setattr(paper_ops, "create_database_engine", lambda settings: engine)
    monkeypatch.setattr(paper_ops, "check_database", lambda candidate: "schema_pending")
    monkeypatch.setattr(paper_ops, "database_revision", lambda candidate: (["old"], "head"))

    with pytest.raises(RuntimeError, match="alembic_not_at_head"):
        await paper_ops.run_preflight(False)

    engine.dispose.assert_called_once()


@pytest.mark.anyio
async def test_start_preflight_refuses_multiple_alembic_heads(monkeypatch):
    create = MagicMock()
    monkeypatch.setattr(paper_ops, "runtime_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(paper_ops, "get_alembic_heads", lambda: ("one", "two"))
    monkeypatch.setattr(paper_ops, "create_database_engine", create)

    with pytest.raises(RuntimeError, match="alembic_expected_single_head"):
        await paper_ops.run_preflight(False)

    create.assert_not_called()


def test_alembic_head_is_derived_from_graph():
    heads = get_alembic_heads()
    assert len(heads) == 1
    assert get_alembic_head() == heads[0]


@pytest.mark.anyio
async def test_degraded_worker_never_submits_buy():
    adapter = AsyncMock()
    worker = AlpacaPaperWorker(MagicMock(), adapter, MagicMock())
    worker.executor.submit = AsyncMock()

    await worker._process_pending_submits(
        account={"equity": "1000"},
        positions=[],
    )

    worker.executor.submit.assert_not_awaited()


def test_inherited_broker_position_is_known_and_blocks_pyramiding():
    position = {
        "symbol": "AAPL",
        "qty": "0.03005596",
        "avg_entry_price": "332.71",
        "current_price": "333.00",
        "market_value": "10.00863368",
    }
    worker = AlpacaPaperWorker(MagicMock(), AsyncMock(), MagicMock())
    worker._validate_positions([position])

    approved, reason = ExecutionGuard.evaluate(
        "BUY",
        "AAPL",
        [position],
        {"equity": "1000"},
        Decimal("1000"),
        state_known=True,
    )
    assert not approved
    assert reason and "no pyramiding" in reason


def test_broker_exposure_at_cap_refuses_buy():
    approved, reason = ExecutionGuard.evaluate(
        "BUY",
        "TSLA",
        [
            {"symbol": "AAPL", "qty": "0.1", "market_value": "10"},
            {"symbol": "SPY", "qty": "0.1", "market_value": "20"},
        ],
        {"equity": "1000"},
        Decimal("1000"),
        state_known=True,
    )
    assert not approved
    assert reason and "Exposição máxima" in reason


@pytest.mark.anyio
async def test_sell_request_uses_exact_quantity_and_no_notional():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "paper-id", "status": "accepted"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AlpacaPaperAdapter("key", "secret", client=client)
    async with adapter:
        await adapter.submit_order(
            symbol="AAPL",
            qty=Decimal("0.03005596"),
            side="sell",
            client_order_id="sell-exact-quantity",
            notional=None,
        )
    await client.aclose()

    assert captured["qty"] == "0.03005596"
    assert "notional" not in captured


def _load_reset_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "reset-paper-baseline.py"
    spec = importlib.util.spec_from_file_location("reset_paper_baseline_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_dry_run_inspection_does_not_open_write_transaction(monkeypatch, tmp_path):
    reset = _load_reset_module()
    engine = MagicMock()
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.scalar.return_value = 0
    connection.execute.return_value.mappings.return_value.first.return_value = {"paused": True}
    monkeypatch.setattr(reset, "database_revision", lambda candidate: (["head"], "head"))
    monkeypatch.setattr(reset, "api_is_active", lambda: False)
    monkeypatch.setattr(reset, "runtime_pid", lambda: None)
    monkeypatch.setattr(reset, "paper_runtime_lock_available", lambda candidate: True)

    async def empty_broker(_settings):
        return {"status": "ACTIVE"}, [], []

    monkeypatch.setattr(reset, "broker_state", empty_broker)
    plan = reset.inspect_plan(
        engine,
        SimpleNamespace(
            postgres_db="trading_bot_dev",
            app_env="local",
            database_role="runtime",
        ),
        tmp_path / "backup.dump",
    )

    assert plan["tables"]
    engine.begin.assert_not_called()


@pytest.mark.parametrize("field", ["broker_positions", "broker_open_orders"])
def test_baseline_reset_refuses_nonempty_broker_state(field):
    reset = _load_reset_module()
    plan = {
        "runtime_pid": None,
        "runtime_api_active": False,
        "runtime_paused": True,
        "runtime_lock_available": True,
        "broker_positions": [],
        "broker_open_orders": [],
    }
    plan[field] = [{"id": "present"}]

    with pytest.raises(RuntimeError, match="broker_has_"):
        reset.validate_confirm_preconditions(plan)


def test_baseline_backup_completes_before_any_database_mutation(monkeypatch, tmp_path):
    reset = _load_reset_module()
    events = []
    monkeypatch.setattr(reset, "create_backup", lambda *args: events.append("backup"))

    async def empty_broker(_settings):
        events.append("broker_recheck")
        return {"cash": "1000"}, [], []

    monkeypatch.setattr(reset, "broker_state", empty_broker)
    monkeypatch.setattr(
        reset,
        "create_clean_baseline",
        lambda *args: events.append("database_mutation") or "run-id",
    )
    plan = {
        "runtime_pid": None,
        "runtime_api_active": False,
        "runtime_paused": True,
        "runtime_lock_available": True,
        "broker_positions": [],
        "broker_open_orders": [],
    }

    reset.perform_confirm(SimpleNamespace(), MagicMock(), plan, tmp_path / "backup.dump")

    assert events == ["backup", "broker_recheck", "database_mutation"]
