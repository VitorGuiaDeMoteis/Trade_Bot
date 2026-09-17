import pytest
import asyncio
from uuid import uuid4
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import insert, select, text
from httpx import AsyncClient, MockTransport, Response

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.worker import AlpacaPaperWorker
from services.alpaca_paper.guard import ExecutionGuard
from services.api.models import paper_orders, broker_orders, risk_decisions, signals, candles, paper_runs, system_controls
from services.api.config import Settings
from sqlalchemy import create_engine

@pytest.fixture
def engine():
    settings = Settings()
    engine = create_engine(settings.database_url)
    return engine

@pytest.fixture
def async_adapter():
    def handler(request):
        # Default mock returning typical responses
        if "/account" in str(request.url):
            return Response(200, json={"status": "ACTIVE", "cash": "100000", "equity": "100000", "portfolio_value": "100000"})
        if "/positions" in str(request.url):
            return Response(200, json=[])
        if "/orders" in str(request.url):
            if request.method == "POST":
                return Response(200, json={"id": "fake_broker_id", "status": "accepted"})
            return Response(200, json=[])
        return Response(404)
        
    client = AsyncClient(transport=MockTransport(handler))
    return AlpacaPaperAdapter("k", "s", client=client)

def insert_baseline(engine):
    with engine.begin() as conn:
        run_id = uuid4()
        conn.execute(insert(paper_runs).values(
            run_id=run_id, mode="REPLAY", provider="alpaca", status="RUNNING",
            initial_cash=100000, cash=100000, fees=0, realized_pnl=0,
            fee_bps=0, slippage_bps=0, dataset={}, dataset_hash="h", step=1,
            created_at=datetime.now(UTC)
        ))
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        stmt = pg_insert(system_controls).values(
            control_id=1, active_run_id=run_id, paused=False, updated_at=datetime.now(UTC)
        )
        conn.execute(stmt.on_conflict_do_update(
            index_elements=['control_id'],
            set_={'active_run_id': run_id}
        ))
        
        # Insert a signal and risk decision
        c_id = uuid4()
        s_id = uuid4()
        from datetime import timedelta
        open_time = datetime.now(UTC)
        conn.execute(insert(candles).values(
            candle_id=c_id, stream_id=uuid4(), sequence=1, symbol="AAPL", provider="alpaca",
            open_time=open_time, close_time=open_time + timedelta(hours=1),
            open=100, high=100, low=100, close=100, volume=100
        ))
        conn.execute(insert(signals).values(
            signal_id=s_id, candle_id=c_id, stream_id=uuid4(), strategy_version="1",
            reason="test", signal_type="BUY", generated_at=datetime.now(UTC)
        ))
        rd_id = uuid4()
        conn.execute(insert(risk_decisions).values(
            decision_id=rd_id, run_id=run_id, signal_id=s_id, decision="APPROVED",
            reason="ok", decided_at=datetime.now(UTC)
        ))
        return run_id, s_id, rd_id


@pytest.mark.anyio
async def test_1_and_2_notional_constraint(engine):
    run_id, s_id, rd_id = insert_baseline(engine)
    order_id = uuid4()
    
    with engine.begin() as conn:
        # Test 2: Quantity-based fails if filled > quantity
        with pytest.raises(Exception):
            conn.execute(insert(paper_orders).values(
                order_id=uuid4(), run_id=run_id, signal_id=s_id, risk_decision_id=rd_id,
                symbol="AAPL", side="BUY", quantity=Decimal("10"), filled_quantity=Decimal("11"),
                status="FILLED", requested_at=datetime.now(UTC), idempotency_key=uuid4(), reason="test"
            ))
            
    with engine.begin() as conn:
        # Test 1 & 2: Notional-based (quantity=0) accepts ANY filled_quantity
        conn.execute(insert(paper_orders).values(
            order_id=order_id, run_id=run_id, signal_id=s_id, risk_decision_id=rd_id,
            symbol="AAPL", side="BUY", quantity=Decimal("0"), filled_quantity=Decimal("0.03005596"),
            status="FILLED", requested_at=datetime.now(UTC), idempotency_key=order_id, reason="test"
        ))
        
        # Verify it persisted exactly
        row = conn.execute(select(paper_orders.c.filled_quantity).where(paper_orders.c.order_id == order_id)).first()
        assert row.filled_quantity == Decimal("0.03005596")


@pytest.mark.anyio
async def test_3_reconciliation_failure_fail_safe(engine, async_adapter):
    run_id, s_id, rd_id = insert_baseline(engine)
    worker = AlpacaPaperWorker(engine, async_adapter, None)
    
    order_id = uuid4()
    b_id = str(uuid4())
    with engine.begin() as conn:
        conn.execute(insert(paper_orders).values(
            order_id=order_id, run_id=run_id, signal_id=s_id, risk_decision_id=rd_id,
            symbol="AAPL", side="BUY", quantity=Decimal("10"), filled_quantity=Decimal("0"),
            status="SUBMITTING", requested_at=datetime.now(UTC), idempotency_key=order_id, reason="test"
        ))
        conn.execute(insert(broker_orders).values(
            order_id=order_id, client_order_id=str(order_id), broker_order_id=b_id,
            status="submitting", filled_quantity=0, last_reconciled_at=datetime.now(UTC)
        ))

    # Mock adapter to return a fill that will cause a constraint violation (qty=11 > 10)
    def handler(request):
        print(f"REQUEST URL: {request.url}")
        if "/account" in str(request.url):
            return Response(200, json={"status": "ACTIVE", "cash": "1000", "equity": "1000", "portfolio_value": "1000"})
        if f"/orders/{b_id}" in str(request.url):
            return Response(200, json={"id": b_id, "status": "filled", "filled_qty": "11.0"})
        if "/positions" in str(request.url):
            return Response(200, json=[])
        return Response(200, json=[])
        
    worker.adapter._client = AsyncClient(transport=MockTransport(handler))
    
    # Run one iteration. The reconciliation should fail due to constraint (11 > 10)
    worker.running = True
    task = asyncio.create_task(worker._run())
    await asyncio.sleep(0.5)
    worker.running = False
    await task
    
    print(f"DEGRADED AT END: {worker.degraded}")
    assert worker.degraded is True


@pytest.mark.anyio
async def test_4_broker_local_divergence(engine):
    # local exposure = 20 (not passed to evaluate directly, Guard uses broker only)
    # broker exposure = 50 -> should REJECT due to MAX_TOTAL_EXPOSURE = 30
    
    broker_positions = [
        {"symbol": "TSLA", "qty": "0.1", "market_value": "50.00"} # Total exposure = $50
    ]
    
    approved, reason = ExecutionGuard.evaluate(
        side="BUY", symbol="AAPL", positions=broker_positions,
        snapshot={"equity": "100"}, last_equity=Decimal("100"),
        in_flight=[]
    )
    
    assert approved is False
    assert "Exposição máxima" in reason


@pytest.mark.anyio
async def test_5_multiple_symbols_incident_cap(engine):
    # 2 symbols in-flight simultaneously with notional = 20
    in_flight = [
        {"symbol": "AAPL", "side": "BUY", "quantity": "0", "requested_notional": "20"},
        {"symbol": "SPY", "side": "BUY", "quantity": "0", "requested_notional": "20"}
    ]
    
    approved, reason = ExecutionGuard.evaluate(
        side="BUY", symbol="TSLA", positions=[],
        snapshot={"equity": "100"}, last_equity=Decimal("100"),
        in_flight=in_flight
    )
    
    # 20 + 20 + 10 (new) = 50 > 30 => Should reject
    assert approved is False
    assert "Exposição máxima" in reason

@pytest.mark.anyio
async def test_6_restart_with_positions(engine, async_adapter):
    # During startup, if preflight fails (e.g. reconcile fails), no new BUY
    worker = AlpacaPaperWorker(engine, async_adapter, None)
    
    # Force _reconcile_active_orders to fail
    def fetch_active():
        raise Exception("DB Down")
    import unittest.mock as mock
    with mock.patch("asyncio.to_thread", side_effect=Exception("DB Down")):
        worker.running = True
        task = asyncio.create_task(worker._run())
        await asyncio.sleep(0.5)
        worker.running = False
        
        try:
            await task
        except:
            pass
            
    assert worker.degraded is True
