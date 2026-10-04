from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from test_market_integration import market as market

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter, AlpacaPaperError
from services.alpaca_paper.executor import AlpacaPaperExecutor
from services.alpaca_paper.guard import ExecutionGuard
from services.alpaca_paper.worker import AlpacaPaperWorker
from services.api.analytics import get_session_analytics


@pytest.fixture
def test_engine(market):
    settings, engine, generator, market_store = market
    return engine

def test_dust_buy_and_sell_policy():
    approved, reason = ExecutionGuard.evaluate(
        side="BUY", symbol="AAPL", positions=[{"symbol": "AAPL", "quantity": "0.0001", "market_value": "0.05"}],
        snapshot={"equity": "1000"}, last_equity=Decimal("1000")
    )
    assert not approved
    assert "no pyramiding" in reason

    approved, reason = ExecutionGuard.evaluate(
        side="SELL", symbol="AAPL", positions=[{"symbol": "AAPL", "quantity": "0.0001", "market_value": "0.05"}],
        snapshot={"equity": "1000"}, last_equity=Decimal("1000")
    )
    assert approved

def test_global_exposure_with_in_flight():
    approved, reason = ExecutionGuard.evaluate(
        side="BUY", symbol="AAPL", positions=[{"symbol": "TSLA", "quantity": "1", "market_value": "15.00"}],
        snapshot={"equity": "1000"}, last_equity=Decimal("1000"),
        in_flight=[{"symbol": "SPY", "side": "BUY", "quantity": "0", "requested_notional": "10.00"}]
    )
    assert not approved
    assert "Exposição máxima total" in reason

def test_two_sells_in_flight_no_short():
    approved, reason = ExecutionGuard.evaluate(
        side="SELL", symbol="AAPL", positions=[{"symbol": "AAPL", "quantity": "0.03", "market_value": "5.00"}],
        snapshot={"equity": "1000"}, last_equity=Decimal("1000"),
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": "0.02"}]
    )
    assert approved

    approved, reason = ExecutionGuard.evaluate(
        side="SELL", symbol="AAPL", positions=[{"symbol": "AAPL", "quantity": "0.03", "market_value": "5.00"}],
        snapshot={"equity": "1000"}, last_equity=Decimal("1000"),
        in_flight=[{"symbol": "AAPL", "side": "SELL", "quantity": "0.03"}]
    )
    assert not approved
    assert "proibida" in reason

@pytest.mark.anyio
async def test_adapter_401_403_raises():
    class DummyResponse:
        status_code = 401
        text = "Unauthorized"
        content = b"Unauthorized"
        def json(self): return {}

    class MockClient:
        async def request(self, *args, **kwargs): return DummyResponse()
            
    adapter = AlpacaPaperAdapter("key", "secret")
    adapter._client = MockClient()
    adapter._own_client = True
    
    with pytest.raises(AlpacaPaperError) as exc:
        await adapter.get_account()
    assert exc.value.status_code == 401

@pytest.mark.anyio
async def test_adapter_404_returns_none():
    class DummyResponse:
        status_code = 404
        text = "Not found"
        content = b"Not found"
        def json(self): return {}

    class MockClient:
        async def request(self, *args, **kwargs): return DummyResponse()
            
    adapter = AlpacaPaperAdapter("key", "secret")
    adapter._client = MockClient()
    adapter._own_client = True
    assert await adapter.get_order_by_id("123") is None

@pytest.mark.anyio
async def test_worker_calls_execution_guard(test_engine):
    # `AlpacaPaperWorker` builds its OWN `AlpacaPaperExecutor` from the adapter, so there is
    # no executor to inject here. The observable proof that the guard ran is that the
    # APPROVED decision is rewritten to REJECTED and NO paper_orders row is written --
    # asserting on an injected double, as this test used to, proved nothing.
    class DummyAdapter:
        async def get_account(self): return {"equity": "1000"}
        async def get_positions(self): return [{"symbol": "AAPL", "quantity": "10", "market_value": "20.00"}]

    worker = AlpacaPaperWorker(test_engine, DummyAdapter(), None)
    # `reconcile_once` is what opens a worker in production. Stand in for it here rather
    # than leaving the worker fail-closed, which made `_process_pending_submits` return
    # before reading a single row (so this test asserted nothing at all).
    worker.degraded = False
    worker.reconciliation_ready = True
    
    run_id, candle_id, signal_id, dec_id = uuid4(), uuid4(), uuid4(), uuid4()
    
    with test_engine.begin() as conn:
        from services.api.models import (
            candles,
            paper_runs,
            risk_decisions,
            signals,
            system_controls,
        )
        conn.execute(paper_runs.insert().values(run_id=run_id, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=''))
        conn.execute(system_controls.insert().values(control_id=1, paused=False, active_run_id=run_id, updated_at=datetime.now(UTC)))
        conn.execute(candles.insert().values(candle_id=candle_id, stream_id=uuid4(), sequence=1, symbol='AAPL', timeframe='1h', provider='alpaca', open_time=datetime(2026, 1, 1, tzinfo=UTC), close_time=datetime(2026, 1, 1, 1, tzinfo=UTC), open=1, high=2, low=1, close=2, volume=10, is_closed=True))
        conn.execute(signals.insert().values(signal_id=signal_id, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.0', reason='test', signal_type='BUY', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec_id, signal_id=signal_id, run_id=run_id, decided_at=datetime.now(UTC), decision='APPROVED', reason='test'))

    try:
        # `last_equity` is required here: without a baseline the BUY fails closed in the
        # Daily Breaker check and never reaches the pyramiding rule under test.
        await worker._process_pending_submits(
            account={"equity": "1000", "cash": "1000", "last_equity": "1000"},
            positions=[{"symbol": "AAPL", "quantity": "10", "market_value": "20.00"}],
        )
        with test_engine.begin() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM paper_orders")).scalar() == 0
            dec = conn.execute(text("SELECT decision, reason FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec_id)}).mappings().first()
            assert dec["decision"] == "REJECTED"
            assert "no pyramiding" in dec["reason"] or "Máximo 1 posição" in dec["reason"]
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec_id)})
            conn.execute(text("DELETE FROM signals WHERE signal_id = :s"), {"s": str(signal_id)})
            conn.execute(text("DELETE FROM candles WHERE candle_id = :c"), {"c": str(candle_id)})
            conn.execute(text("DELETE FROM system_controls"))
            conn.execute(text("DELETE FROM paper_runs WHERE run_id = :r"), {"r": str(run_id)})

@pytest.mark.anyio
async def test_worker_snapshot_runs_without_nameerror(test_engine):
    # This test guards a historical crash: the snapshot writer referenced an undefined name
    # while summing unrealized P&L. The contract under test is that the snapshot persists
    # correctly -- it never claimed to clear `degraded` (only `reconcile_once` does that),
    # so that assertion asserted nothing about the code path it meant to cover.
    class DummyAdapter:
        async def get_account(self): return {
            "cash": "500",
            "equity": "1000",
            "portfolio_value": "1000",
            "buying_power": "1000",
        }
        async def _request(self, method, endpoint): return [{"symbol": "AAPL", "qty": "1", "avg_entry_price": "10", "current_price": "15", "market_value": "15", "unrealized_pl": "5"}]
        async def get_positions(self): return [{"symbol": "AAPL", "qty": "1", "avg_entry_price": "10", "current_price": "15", "market_value": "15", "unrealized_pl": "5"}]
            
    worker = AlpacaPaperWorker(test_engine, DummyAdapter(), None)
    await worker._snapshot_broker_portfolio()
    
    with test_engine.begin() as conn:
        snap = conn.execute(text("SELECT status, unrealized_pnl FROM broker_portfolio_snapshots WHERE provider = 'alpaca'")).mappings().first()
        assert snap["status"] == "ACTIVE"
        assert snap["unrealized_pnl"] == Decimal("5")

def test_analytics_run_isolation_and_realized_pnl(test_engine):
    run_1, run_2 = str(uuid4()), str(uuid4())
    order_1, order_2, exit_order_1 = str(uuid4()), str(uuid4()), str(uuid4())
    fill_1_1, fill_1_2, fill_2_1 = str(uuid4()), str(uuid4()), str(uuid4())
    
    with test_engine.begin() as conn:
        from services.api.models import paper_runs
        conn.execute(paper_runs.insert().values(run_id=run_1, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=""))
        conn.execute(paper_runs.insert().values(run_id=run_2, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=""))
        
        conn.execute(text("SET session_replication_role = replica;"))
        dec_1 = str(uuid4())
        conn.execute(text("INSERT INTO risk_decisions (decision_id, signal_id, run_id, decided_at, decision, reason) VALUES (:d, :s, :r, now(), 'APPROVED', '')"), {"d": dec_1, "s": str(uuid4()), "r": run_1})
        dec_3 = str(uuid4())
        conn.execute(text("INSERT INTO risk_decisions (decision_id, signal_id, run_id, decided_at, decision, reason) VALUES (:d, :s, :r, now(), 'APPROVED', '')"), {"d": dec_3, "s": str(uuid4()), "r": run_1})
        dec_2 = str(uuid4())
        conn.execute(text("INSERT INTO risk_decisions (decision_id, signal_id, run_id, decided_at, decision, reason) VALUES (:d, :s, :r, now(), 'APPROVED', '')"), {"d": dec_2, "s": str(uuid4()), "r": run_2})

        conn.execute(text("INSERT INTO paper_orders (order_id, signal_id, run_id, risk_decision_id, symbol, side, quantity, filled_quantity, status, requested_at, idempotency_key, reason) VALUES (:o, :s, :r, :d, 'AAPL', 'BUY', 1, 1, 'FILLED', now(), :o, '')"), {"o": order_1, "r": run_1, "d": dec_1, "s": str(uuid4())})
        conn.execute(text("INSERT INTO broker_orders (order_id, client_order_id, status, filled_quantity, requested_quantity, requested_notional, last_reconciled_at) VALUES (:o, 'c1', 'filled', 1, 1, 10, now())"), {"o": order_1})
        conn.execute(text("INSERT INTO broker_fills (broker_fill_id, order_id, quantity, price, fee, filled_at) VALUES (:f, :o, 1, 10, 1, now() - interval '30 minutes')"), {"f": fill_1_1, "o": order_1})
        
        conn.execute(text("INSERT INTO paper_orders (order_id, signal_id, run_id, risk_decision_id, symbol, side, quantity, filled_quantity, status, requested_at, idempotency_key, reason) VALUES (:o, :s, :r, :d, 'AAPL', 'SELL', 1, 1, 'FILLED', now(), :o, '')"), {"o": exit_order_1, "r": run_1, "d": dec_3, "s": str(uuid4())})
        conn.execute(text("INSERT INTO broker_orders (order_id, client_order_id, status, filled_quantity, requested_quantity, requested_notional, last_reconciled_at) VALUES (:o, 'c1e', 'filled', 1, 1, 10, now())"), {"o": exit_order_1})
        conn.execute(text("INSERT INTO broker_fills (broker_fill_id, order_id, quantity, price, fee, filled_at) VALUES (:f, :o, 1, 20, 1, now() - interval '20 minutes')"), {"f": fill_1_2, "o": exit_order_1})
        
        conn.execute(text("INSERT INTO paper_orders (order_id, signal_id, run_id, risk_decision_id, symbol, side, quantity, filled_quantity, status, requested_at, idempotency_key, reason) VALUES (:o, :s, :r, :d, 'TSLA', 'BUY', 1, 1, 'FILLED', now(), :o, '')"), {"o": order_2, "r": run_2, "d": dec_2, "s": str(uuid4())})
        conn.execute(text("INSERT INTO broker_orders (order_id, client_order_id, status, filled_quantity, requested_quantity, requested_notional, last_reconciled_at) VALUES (:o, 'c2', 'filled', 1, 1, 10, now())"), {"o": order_2})
        conn.execute(text("INSERT INTO broker_fills (broker_fill_id, order_id, quantity, price, fee, filled_at) VALUES (:f, :o, 1, 50, 0, now() - interval '10 minutes')"), {"f": fill_2_1, "o": order_2})
        
        conn.execute(text("SET session_replication_role = DEFAULT;"))

    try:
        with test_engine.begin() as conn:
            analytics_1 = get_session_analytics(conn, run_1)
            analytics_2 = get_session_analytics(conn, run_2)
            
        assert len(analytics_1["closed_trades"]) == 1
        assert float(analytics_1["pnl_realized"]) == 8.0
        assert len(analytics_2["closed_trades"]) == 0
        assert float(analytics_2["pnl_realized"]) == 0.0
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM broker_fills"))
            conn.execute(text("DELETE FROM broker_orders"))
            conn.execute(text("DELETE FROM paper_orders"))
            conn.execute(text("DELETE FROM risk_decisions"))
            conn.execute(text("DELETE FROM paper_runs"))




@pytest.mark.anyio
async def test_worker_sell_uses_exact_quantity_and_no_notional(test_engine):
    class DummyAdapter:
        async def get_account(self): return {"equity": "1000", "cash": "1000", "buying_power": "1000"}
        async def get_positions(self): return [{"symbol": "TSLA", "qty": "0.5", "quantity": "0.5", "market_value": "15.00"}]
        async def submit_order(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "client_order_id": kwargs.get("client_order_id"), "status": "accepted"}
        async def get_order_by_client_id(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "status": "accepted", "filled_qty": "0", "filled_avg_price": "0"}
            
    worker = AlpacaPaperWorker(test_engine, DummyAdapter(), None)
    worker.degraded = False
    worker.reconciliation_ready = True
    
    run_id, candle_id, signal_id, dec_id = uuid4(), uuid4(), uuid4(), uuid4()
    
    with test_engine.begin() as conn:
        from services.api.models import (
            candles,
            paper_runs,
            risk_decisions,
            signals,
            system_controls,
        )
        conn.execute(paper_runs.insert().values(run_id=run_id, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=''))
        conn.execute(system_controls.insert().values(control_id=1, paused=False, active_run_id=run_id, updated_at=datetime.now(UTC)))
        conn.execute(candles.insert().values(candle_id=candle_id, stream_id=uuid4(), sequence=1, symbol='TSLA', timeframe='1h', provider='alpaca', open_time=datetime(2026, 1, 1, tzinfo=UTC), close_time=datetime(2026, 1, 1, 1, tzinfo=UTC), open=1, high=2, low=1, close=2, volume=10, is_closed=True))
        conn.execute(signals.insert().values(signal_id=signal_id, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.0', reason='test', signal_type='SELL', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec_id, signal_id=signal_id, run_id=run_id, decided_at=datetime.now(UTC), decision='APPROVED', reason='test'))

    try:
        await worker._process_pending_submits(
            account={"equity": "1000", "cash": "1000", "buying_power": "1000"},
            positions=[
                {"symbol": "TSLA", "qty": "0.5", "quantity": "0.5", "market_value": "15.00"}
            ],
        )
        with test_engine.begin() as conn:
            bo = conn.execute(text("SELECT * FROM broker_orders LIMIT 1")).mappings().first()
            po = conn.execute(text("SELECT * FROM paper_orders LIMIT 1")).mappings().first()
            if not bo:
                decision = conn.execute(text("SELECT * FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec_id)}).mappings().first()
                raise AssertionError(f"SELL failed: {decision['reason']}")
            
            assert bo["requested_notional"] is None
            assert po["quantity"] == Decimal("0.5")
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM broker_orders"))
            conn.execute(text("DELETE FROM paper_orders"))
            conn.execute(text("DELETE FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec_id)})
            conn.execute(text("DELETE FROM signals WHERE signal_id = :s"), {"s": str(signal_id)})
            conn.execute(text("DELETE FROM candles WHERE candle_id = :c"), {"c": str(candle_id)})
            conn.execute(text("DELETE FROM system_controls"))
            conn.execute(text("DELETE FROM paper_runs WHERE run_id = :r"), {"r": str(run_id)})



@pytest.mark.anyio
async def test_worker_inflight_prevents_pyramiding(test_engine):
    class DummyAdapter:
        async def get_account(self): return {"equity": "1000", "cash": "1000", "buying_power": "1000"}
        async def get_positions(self): return []
        async def submit_order(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "client_order_id": kwargs.get("client_order_id"), "status": "accepted"}
        async def get_order_by_client_id(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "status": "accepted", "filled_qty": "0", "filled_avg_price": "0"}
            
    worker = AlpacaPaperWorker(test_engine, DummyAdapter(), None)
    # A fresh worker starts degraded (`AlpacaPaperWorker.__init__` sets degraded=True /
    # reconciliation_ready=False) and `_process_pending_submits` returns at its first
    # line while that holds -- so the worker must be OPENED the way `reconcile_once`
    # opens it in production, otherwise nothing is ever fetched or submitted.
    worker.degraded = False
    worker.reconciliation_ready = True
    
    run_id, candle_id, sig1, sig2, dec1, dec2 = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    
    with test_engine.begin() as conn:
        from services.api.models import (
            candles,
            paper_runs,
            risk_decisions,
            signals,
            system_controls,
        )
        conn.execute(paper_runs.insert().values(run_id=run_id, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=''))
        conn.execute(system_controls.insert().values(control_id=1, paused=False, active_run_id=run_id, updated_at=datetime.now(UTC)))
        conn.execute(candles.insert().values(candle_id=candle_id, stream_id=uuid4(), sequence=1, symbol='SPY', timeframe='1h', provider='alpaca', open_time=datetime(2026, 1, 1, tzinfo=UTC), close_time=datetime(2026, 1, 1, 1, tzinfo=UTC), open=1, high=2, low=1, close=2, volume=10, is_closed=True))
        
        # Two BUY signals in the same batch
        conn.execute(signals.insert().values(signal_id=sig1, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.0', reason='test', signal_type='BUY', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec1, signal_id=sig1, run_id=run_id, decided_at=datetime.now(UTC), decision='APPROVED', reason='test'))
        
        conn.execute(signals.insert().values(signal_id=sig2, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.1', reason='test', signal_type='BUY', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec2, signal_id=sig2, run_id=run_id, decided_at=datetime.now(UTC) + timedelta(seconds=1), decision='APPROVED', reason='test'))

    try:
        # `last_equity` is the Daily Breaker baseline: without it the guard fails CLOSED
        # on the first BUY and no order is ever submitted, so the assertion below would
        # hold for the wrong reason. Positions come from the broker, not the fixture.
        await worker._process_pending_submits(
            account={
                "equity": "1000",
                "cash": "1000",
                "last_equity": "1000",
                "buying_power": "1000",
            },
            positions=[],
        )
        with test_engine.begin() as conn:
            # Only 1 order should be in paper_orders
            count = len(conn.execute(text("SELECT * FROM paper_orders")).mappings().all())
            assert count == 1
            
            d2 = conn.execute(text("SELECT decision, reason FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec2)}).mappings().first()
            assert d2["decision"] == "REJECTED"
            assert "no pyramiding" in d2["reason"].lower() or "1 posição" in d2["reason"].lower() or "in-flight" in d2["reason"].lower()
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM broker_orders"))
            conn.execute(text("DELETE FROM paper_orders"))
            conn.execute(text("DELETE FROM risk_decisions WHERE decision_id IN (:d1, :d2)"), {"d1": str(dec1), "d2": str(dec2)})
            conn.execute(text("DELETE FROM signals WHERE signal_id IN (:s1, :s2)"), {"s1": str(sig1), "s2": str(sig2)})
            conn.execute(text("DELETE FROM candles WHERE candle_id = :c"), {"c": str(candle_id)})
            conn.execute(text("DELETE FROM system_controls"))
            conn.execute(text("DELETE FROM paper_runs WHERE run_id = :r"), {"r": str(run_id)})

@pytest.mark.anyio
async def test_worker_inflight_double_sell(test_engine):
    class DummyAdapter:
        async def get_account(self): return {"equity": "1000", "cash": "1000", "buying_power": "1000"}
        async def get_positions(self): return [{"symbol": "AAPL", "qty": "0.03", "quantity": "0.03", "market_value": "5.00"}]
        async def submit_order(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "client_order_id": kwargs.get("client_order_id"), "status": "accepted"}
        async def get_order_by_client_id(self, *args, **kwargs):
            import uuid
            return {"id": str(uuid.uuid4()), "status": "accepted", "filled_qty": "0", "filled_avg_price": "0"}
            
    worker = AlpacaPaperWorker(test_engine, DummyAdapter(), None)
    # Same gate as `test_worker_inflight_prevents_pyramiding`: open the worker the way
    # `reconcile_once` does, otherwise `_process_pending_submits` returns immediately.
    worker.degraded = False
    worker.reconciliation_ready = True
    
    run_id, candle_id, sig1, sig2, dec1, dec2 = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    
    with test_engine.begin() as conn:
        from services.api.models import (
            candles,
            paper_runs,
            risk_decisions,
            signals,
            system_controls,
        )
        conn.execute(paper_runs.insert().values(run_id=run_id, created_at=datetime.now(UTC), mode='REPLAY', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=''))
        conn.execute(system_controls.insert().values(control_id=1, paused=False, active_run_id=run_id, updated_at=datetime.now(UTC)))
        conn.execute(candles.insert().values(candle_id=candle_id, stream_id=uuid4(), sequence=1, symbol='AAPL', timeframe='1h', provider='alpaca', open_time=datetime(2026, 1, 1, tzinfo=UTC), close_time=datetime(2026, 1, 1, 1, tzinfo=UTC), open=1, high=2, low=1, close=2, volume=10, is_closed=True))
        
        # Two SELL signals in the same batch
        conn.execute(signals.insert().values(signal_id=sig1, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.0', reason='test', signal_type='SELL', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec1, signal_id=sig1, run_id=run_id, decided_at=datetime.now(UTC), decision='APPROVED', reason='test'))
        
        conn.execute(signals.insert().values(signal_id=sig2, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.1', reason='test', signal_type='SELL', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec2, signal_id=sig2, run_id=run_id, decided_at=datetime.now(UTC) + timedelta(seconds=1), decision='APPROVED', reason='test'))

    try:
        # Positions must be the BROKER's (0.03 AAPL), not the fixture's: the second SELL
        # is only rejected because the in-flight quantity is no longer available to sell.
        await worker._process_pending_submits(
            account={
                "equity": "1000",
                "cash": "1000",
                "last_equity": "1000",
                "buying_power": "1000",
            },
            positions=[
                {"symbol": "AAPL", "qty": "0.03", "quantity": "0.03", "market_value": "5.00"}
            ],
        )
        with test_engine.begin() as conn:
            count = len(conn.execute(text("SELECT * FROM paper_orders")).mappings().all())
            assert count == 1
            
            d2 = conn.execute(text("SELECT decision, reason FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec2)}).mappings().first()
            assert d2["decision"] == "REJECTED"
            assert "proibida" in d2["reason"].lower() or "short" in d2["reason"].lower() or "indisponível" in d2["reason"].lower()
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM broker_orders"))
            conn.execute(text("DELETE FROM paper_orders"))
            conn.execute(text("DELETE FROM risk_decisions WHERE decision_id IN (:d1, :d2)"), {"d1": str(dec1), "d2": str(dec2)})
            conn.execute(text("DELETE FROM signals WHERE signal_id IN (:s1, :s2)"), {"s1": str(sig1), "s2": str(sig2)})
            conn.execute(text("DELETE FROM candles WHERE candle_id = :c"), {"c": str(candle_id)})
            conn.execute(text("DELETE FROM system_controls"))
            conn.execute(text("DELETE FROM paper_runs WHERE run_id = :r"), {"r": str(run_id)})


@pytest.mark.anyio
async def test_submit_timeout_path_reconciles_by_client_order_id(test_engine):
    """Guards the NameError that hid in two DummyAdapter stubs in this file.

    `get_order_by_client_id` referenced a `uuid` module object that only existed as a
    function-local import inside the sibling `submit_order`, so calling it raised
    `NameError`. Nothing caught it: the inflight tests never take the timeout branch,
    and `submit()` wraps the whole broker call in `except Exception`, so the NameError
    was absorbed into the generic `network_error` result and the reconciliation
    silently never happened. Green tests, broken idempotency.
    """
    class TimeoutAdapter:
        async def submit_order(self, **kwargs):
            from services.alpaca_paper.adapter import AlpacaPaperError
            # status_code 500 is deliberately NOT in (403, 422): that is what makes
            # `submit` fall through to `_handle_timeout_or_disconnect`.
            raise AlpacaPaperError("boom", code="timeout", status_code=500)

        async def get_order_by_client_id(self, client_order_id):
            import uuid
            return {
                "id": str(uuid.uuid4()),
                "status": "accepted",
                "filled_qty": "0",
                "filled_avg_price": "0",
            }

    from services.api.models import (
        candles,
        paper_runs,
        risk_decisions,
        signals,
    )

    run_id, order_id = uuid4(), uuid4()
    candle_id, signal_id, dec_id = uuid4(), uuid4(), uuid4()

    with test_engine.begin() as conn:
        conn.execute(paper_runs.insert().values(run_id=run_id, created_at=datetime.now(UTC), mode='ALPACA_PAPER', provider='alpaca', status='RUNNING', initial_cash=1000, cash=1000, step=1, fee_bps=0, fees=0, realized_pnl=0, slippage_bps=0, dataset=[], dataset_hash=''))
        conn.execute(candles.insert().values(candle_id=candle_id, stream_id=uuid4(), sequence=1, symbol='AAPL', timeframe='1h', provider='alpaca', open_time=datetime(2026, 1, 1, tzinfo=UTC), close_time=datetime(2026, 1, 1, 1, tzinfo=UTC), open=1, high=2, low=1, close=2, volume=10, is_closed=True))
        conn.execute(signals.insert().values(signal_id=signal_id, candle_id=candle_id, stream_id=uuid4(), strategy_version='1.0', reason='test', signal_type='BUY', generated_at=datetime.now(UTC)))
        conn.execute(risk_decisions.insert().values(decision_id=dec_id, signal_id=signal_id, run_id=run_id, decided_at=datetime.now(UTC), decision='APPROVED', reason='test'))

    executor = AlpacaPaperExecutor(TimeoutAdapter())
    try:
        result = await executor.submit(
            engine=test_engine,
            run_id=run_id,
            signal_id=signal_id,
            risk=RiskDecision(
                decision_id=dec_id, signal_id=signal_id, decision="APPROVED",
                reason="test", decided_at=datetime.now(UTC),
            ),
            symbol="AAPL",
            side="BUY",
            quantity=Decimal("1"),
            order_id=order_id,
            requested_at=datetime.now(UTC),
        )
        assert result.status == "REJECTED"
        assert result.reason == "network_error"

        with test_engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT b.broker_order_id, b.status AS broker_status, p.status AS paper_status "
                    "FROM broker_orders b JOIN paper_orders p USING (order_id) "
                    "WHERE b.order_id = :o"
                ),
                {"o": str(order_id)},
            ).mappings().first()

        # The reconciliation ran: the broker stub answered, so the broker row now carries
        # the remote id/status that `get_order_by_client_id` returned.
        assert row is not None
        assert row["broker_order_id"] is not None, "timeout reconciliation never ran"
        assert row["broker_status"] == "accepted"
        assert row["paper_status"] == "ACCEPTED"
    finally:
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM broker_orders WHERE order_id = :o"), {"o": str(order_id)})
            conn.execute(text("DELETE FROM paper_orders WHERE order_id = :o"), {"o": str(order_id)})
            conn.execute(text("DELETE FROM risk_decisions WHERE decision_id = :d"), {"d": str(dec_id)})
            conn.execute(text("DELETE FROM signals WHERE signal_id = :s"), {"s": str(signal_id)})
            conn.execute(text("DELETE FROM candles WHERE candle_id = :c"), {"c": str(candle_id)})
            conn.execute(text("DELETE FROM paper_runs WHERE run_id = :r"), {"r": str(run_id)})
