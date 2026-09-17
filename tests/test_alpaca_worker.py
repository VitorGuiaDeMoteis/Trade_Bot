import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import select

from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.worker import AlpacaPaperWorker
from services.api.config import Settings
from services.api.database import create_database_engine
from services.api.models import (
    broker_orders,
    metadata,
    paper_orders,
    paper_runs,
    risk_decisions,
    signals,
    system_controls,
)


@pytest.fixture
def engine():
    settings = Settings(
        postgres_db="trading_bot_test",
            postgres_port=55432,
            postgres_user="test_only",
            postgres_password="test_only",
        market_data_provider="alpaca",
        execution_mode="alpaca_paper",
        alpaca_api_key_id="test",
        alpaca_api_secret_key="test",
    )
    eng = create_database_engine(settings)
    metadata.drop_all(eng)
    metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def adapter_mock():
    mock = AsyncMock(spec=AlpacaPaperAdapter)
    mock.get_account.return_value = {"status": "ACTIVE"}
    return mock


@pytest.fixture
def settings():
    return Settings(
        postgres_db="trading_bot_test",
            postgres_port=55432,
            postgres_user="test_only",
            postgres_password="test_only",
        market_data_provider="alpaca",
        execution_mode="alpaca_paper",
        alpaca_api_key_id="test",
        alpaca_api_secret_key="test",
    )


@pytest.mark.anyio
async def test_worker_preflight(engine, adapter_mock, settings):
    worker = AlpacaPaperWorker(engine, adapter_mock, settings)
    assert await worker.preflight()

    adapter_mock.get_account.return_value = {"status": "INACTIVE"}
    assert not await worker.preflight()


@pytest.mark.anyio
async def test_worker_startup_reconciliation(engine, adapter_mock, settings):
    run_id = uuid4()
    with engine.begin() as c:
        c.execute(
            paper_runs.insert().values(
                run_id=run_id,
                mode="REPLAY",
                status="RUNNING",
                provider="alpaca",
                initial_cash=1000,
                cash=1000,
                fees=0,
                realized_pnl=0,
                fee_bps=1,
                slippage_bps=1,
                step=1,
                dataset_hash="hash",
                dataset=[],
                created_at=datetime.now(UTC),
            )
        )
        c.execute(
            system_controls.insert().values(
                active_run_id=run_id, paused=False, updated_at=datetime.now(UTC)
            )
        )

        signal_id = uuid4()
        candle_id = uuid4()
        from services.api.models import candles

        c.execute(
            candles.insert().values(
                candle_id=candle_id,
                stream_id=uuid4(),
                sequence=1,
                symbol="SPY",
                timeframe="1h",
                provider="alpaca",
                open_time=datetime(2026, 1, 1, tzinfo=UTC),
                close_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
                is_closed=True,
            )
        )
        c.execute(
            signals.insert().values(
                signal_id=signal_id,
                candle_id=candle_id,
                stream_id=uuid4(),
                strategy_version="1.0",
                reason="test",
                signal_type="BUY",
                generated_at=datetime.now(UTC),
            )
        )

        decision_id = uuid4()
        c.execute(
            risk_decisions.insert().values(
                decision_id=decision_id, run_id=run_id,
                signal_id=signal_id,
                decision="APPROVED",
                reason="test",
                decided_at=datetime.now(UTC),
            )
        )

        order_id = uuid5(run_id, str(decision_id))

        c.execute(
            paper_orders.insert().values(
                order_id=order_id,
                run_id=run_id,
                signal_id=signal_id,
                risk_decision_id=decision_id,
                symbol="SPY",
                side="BUY",
                quantity=1,
                status="SUBMITTING",
                requested_at=datetime.now(UTC),
                idempotency_key=order_id,
                reason="intent_persisted",
            )
        )
        c.execute(
            broker_orders.insert().values(
                order_id=order_id,
                client_order_id=f"m7_{order_id.hex}",
                status="submitting",
                requested_quantity=Decimal("1"),
                filled_quantity=Decimal("0"),
                last_reconciled_at=datetime.now(UTC),
            )
        )

    worker = AlpacaPaperWorker(engine, adapter_mock, settings)

    adapter_mock.get_order_by_client_id.return_value = {
        "id": "broker_order_123",
        "status": "filled",
        "filled_qty": "1",
    }
    adapter_mock.get_fills.return_value = []

    await worker._reconcile_active_orders()

    with engine.connect() as c:
        row = (
            c.execute(select(paper_orders).where(paper_orders.c.order_id == order_id))
            .mappings()
            .one()
        )
        assert row["status"] == "FILLED"
        assert row["filled_quantity"] == 1


@pytest.mark.anyio
async def test_worker_process_pending_submits_idempotency(engine, adapter_mock, settings):
    run_id = uuid4()
    signal_id = uuid4()
    decision_id = uuid4()

    with engine.begin() as c:
        c.execute(
            paper_runs.insert().values(
                run_id=run_id,
                mode="REPLAY",
                status="RUNNING",
                provider="alpaca",
                initial_cash=1000,
                cash=1000,
                fees=0,
                realized_pnl=0,
                fee_bps=1,
                slippage_bps=1,
                step=1,
                dataset_hash="hash",
                dataset=[],
                created_at=datetime.now(UTC),
            )
        )
        c.execute(
            system_controls.insert().values(
                active_run_id=run_id, paused=False, updated_at=datetime.now(UTC)
            )
        )
        candle_id = uuid4()
        from services.api.models import candles

        c.execute(
            candles.insert().values(
                candle_id=candle_id,
                stream_id=uuid4(),
                sequence=1,
                symbol="SPY",
                timeframe="1h",
                provider="alpaca",
                open_time=datetime(2026, 1, 1, tzinfo=UTC),
                close_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
                is_closed=True,
            )
        )
        c.execute(
            signals.insert().values(
                signal_id=signal_id,
                candle_id=candle_id,
                stream_id=uuid4(),
                strategy_version="1.0",
                reason="test",
                signal_type="BUY",
                generated_at=datetime.now(UTC),
            )
        )
        c.execute(
            risk_decisions.insert().values(
                decision_id=decision_id, run_id=run_id,
                signal_id=signal_id,
                decision="APPROVED",
                reason="test",
                decided_at=datetime.now(UTC),
            )
        )

    worker1 = AlpacaPaperWorker(engine, adapter_mock, settings)
    worker2 = AlpacaPaperWorker(engine, adapter_mock, settings)


    adapter_mock.submit_order.return_value = {"id": "broker_order_123", "status": "accepted"}
    adapter_mock.get_account.return_value = {"equity": "1000"}
    adapter_mock.get_positions.return_value = []

    for worker in (worker1, worker2):
        worker.degraded = False
        worker.reconciliation_ready = True

    await asyncio.gather(
        worker1._process_pending_submits(
            account={"equity": "1000"}, positions=[]
        ),
        worker2._process_pending_submits(
            account={"equity": "1000"}, positions=[]
        ),
    )

    assert adapter_mock.submit_order.call_count == 1


@pytest.fixture
def anyio_backend():
    return "asyncio"
