import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient, MockTransport, Response
from test_market_integration import market as market

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.executor import AlpacaPaperExecutor


@pytest.fixture
def db_connection(market):
    settings, engine, generator, market_store = market
    from services.api.models import candles, paper_runs, risk_decisions, signals

    with engine.begin() as conn:
        run_id, candle_id, stream_id, signal_id, risk_id = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        now = datetime.now(UTC)
        conn.execute(
            paper_runs.insert().values(
                run_id=run_id,
                mode="REPLAY",
                provider="simulator",
                status="RUNNING",
                initial_cash=10000,
                cash=10000,
                fees=0,
                realized_pnl=0,
                step=1,
                fee_bps=0,
                slippage_bps=0,
                dataset=[],
                dataset_hash="hash",
                created_at=now,
            )
        )
        conn.execute(
            candles.insert().values(
                candle_id=candle_id,
                stream_id=stream_id,
                sequence=1,
                symbol="AAPL",
                timeframe="1h",
                provider="simulator",
                open_time=now,
                close_time=now + timedelta(hours=1),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000,
                is_closed=True,
            )
        )
        conn.execute(
            signals.insert().values(
                signal_id=signal_id,
                candle_id=candle_id,
                stream_id=stream_id,
                strategy_version="1",
                reason="test",
                signal_type="BUY",
                generated_at=datetime.now(UTC),
            )
        )
        conn.execute(
            risk_decisions.insert().values(
                decision_id=risk_id,
                signal_id=signal_id,
                decision="APPROVED",
                reason="test",
                decided_at=datetime.now(UTC),
            )
        )
        yield conn, run_id, signal_id, risk_id


@pytest.mark.anyio
async def test_duplicate_intent_one_post(db_connection):
    conn, run_id, signal_id, risk_id = db_connection
    post_count = 0

    def handler(request):
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            return Response(200, json={"id": "alpaca-123", "status": "accepted"})
        return Response(200, json={"id": "alpaca-123", "status": "accepted"})

    adapter = AlpacaPaperAdapter("k", "s", AsyncClient(transport=MockTransport(handler)))
    executor = AlpacaPaperExecutor(adapter)

    order_id = uuid4()
    risk = RiskDecision(
        decision_id=risk_id,
        signal_id=signal_id,
        decision="APPROVED",
        reason="test",
        decided_at=datetime.now(UTC),
    )

    res1 = await executor.submit(
        conn, run_id, signal_id, risk, "AAPL", "BUY", 10, order_id, datetime.now(UTC)
    )
    assert res1.status == "ACCEPTED"
    assert post_count == 1

    res2 = await executor.submit(
        conn, run_id, signal_id, risk, "AAPL", "BUY", 10, order_id, datetime.now(UTC)
    )
    assert res2.status == "UNKNOWN"
    assert res2.reason == "duplicate_intent"
    assert post_count == 1


@pytest.mark.anyio
async def test_concurrent_intent_one_post(db_connection):
    conn, run_id, signal_id, risk_id = db_connection
    post_count = 0

    async def slow_handler(request):
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            await asyncio.sleep(0.1)
            return Response(200, json={"id": "alpaca-456", "status": "accepted"})
        return Response(200, json={"id": "alpaca-456", "status": "accepted"})

    adapter = AlpacaPaperAdapter("k", "s", AsyncClient(transport=MockTransport(slow_handler)))
    executor = AlpacaPaperExecutor(adapter)

    order_id = uuid4()
    risk = RiskDecision(
        decision_id=risk_id,
        signal_id=signal_id,
        decision="APPROVED",
        reason="test",
        decided_at=datetime.now(UTC),
    )

    await asyncio.gather(
        executor.submit(
            conn, run_id, signal_id, risk, "AAPL", "BUY", 10, order_id, datetime.now(UTC)
        ),
        executor.submit(
            conn, run_id, signal_id, risk, "AAPL", "BUY", 10, order_id, datetime.now(UTC)
        ),
        return_exceptions=True,
    )

    assert post_count == 1


@pytest.mark.anyio
async def test_reconcile_order_partially_filled(db_connection):
    conn, run_id, signal_id, risk_id = db_connection

    order_id = uuid4()
    client_order_id = f"m7_{order_id.hex}"

    from sqlalchemy import select

    from services.api.models import broker_fills, broker_orders, paper_orders

    conn.execute(
        paper_orders.insert().values(
            order_id=order_id,
            run_id=run_id,
            signal_id=signal_id,
            risk_decision_id=risk_id,
            symbol="AAPL",
            side="BUY",
            quantity=10,
            filled_quantity=0,
            status="SUBMITTING",
            requested_at=datetime.now(UTC),
            idempotency_key=order_id,
            reason="test",
        )
    )
    conn.execute(
        broker_orders.insert().values(
            order_id=order_id,
            client_order_id=client_order_id,
            status="submitting",
            requested_quantity=Decimal(10),
            filled_quantity=Decimal(0),
            last_reconciled_at=datetime.now(UTC),
        )
    )

    calls = []

    async def mock_request(method, path, params=None, **kwargs):
        calls.append((method, path, params))
        if path.endswith(client_order_id):
            return {"id": "broker-123", "status": "partially_filled", "filled_qty": "4.5"}
        if path == "/account/activities/FILL":
            return [
                {"id": "fill-1", "qty": "2", "price": "100.0"},
                {"id": "fill-2", "qty": "2.5", "price": "101.0"},
            ]
        return None

    class DummyAdapter:
        async def get_order_by_client_id(self, client_id):
            return await mock_request("GET", f"/orders:by_client_order_id/{client_id}")

        async def get_order_by_id(self, id):
            return await mock_request("GET", f"/orders/{id}")

        async def get_fills(self, id):
            return await mock_request("GET", "/account/activities/FILL", {"order_id": id})

    executor = AlpacaPaperExecutor(DummyAdapter())
    await executor.reconcile_order(conn, order_id)

    # Check states
    paper = conn.execute(
        select(paper_orders.c.status, paper_orders.c.filled_quantity).where(
            paper_orders.c.order_id == order_id
        )
    ).first()
    assert paper.status == "PARTIALLY_FILLED"
    assert paper.filled_quantity == 4  # int(4.5)

    broker = conn.execute(
        select(broker_orders.c.status, broker_orders.c.filled_quantity).where(
            broker_orders.c.order_id == order_id
        )
    ).first()
    assert broker.status == "partially_filled"
    assert broker.filled_quantity == Decimal("4.5")

    fills = conn.execute(
        select(broker_fills.c.broker_fill_id).where(broker_fills.c.order_id == order_id)
    ).fetchall()
    assert len(fills) == 2
    assert fills[0][0] == "fill-1"
    assert fills[1][0] == "fill-2"
