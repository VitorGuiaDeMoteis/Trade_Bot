import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from packages.contracts.broker import (
    BrokerAccount,
    BrokerClock,
    BrokerOrder,
    BrokerPosition,
    ExternalBroker,
)
from services.api.live_paper_runtime import LivePaperExecutionRuntime


class FakeExternalBroker(ExternalBroker):
    def __init__(self):
        self.orders_submitted = []
        self.positions = []
        self.is_open = True

    async def get_account(self) -> BrokerAccount:
        return BrokerAccount("USD", Decimal("10000"), Decimal("10000"), Decimal("20000"))

    async def get_positions(self) -> list[BrokerPosition]:
        return self.positions

    async def get_orders(self) -> list[BrokerOrder]:
        return []

    async def get_order_by_client_order_id(self, client_order_id: str):
        return None

    async def submit_order(
        self, symbol: str, side: str, quantity: int, client_order_id: str
    ) -> BrokerOrder:
        self.orders_submitted.append((symbol, side, quantity, client_order_id))
        return BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id=str(uuid4()),
            symbol=symbol,
            side=side,
            status="accepted",
            requested_qty=quantity,
            filled_qty=0,
            filled_avg_price=Decimal("0"),
            submitted_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def get_clock(self) -> BrokerClock:
        return BrokerClock(is_open=self.is_open, timestamp=datetime.now(UTC))


@pytest.fixture
def fake_broker():
    return FakeExternalBroker()


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_disarmed_no_post(fake_broker, market):
    _, engine, _, _ = market
    runtime = LivePaperExecutionRuntime(fake_broker, engine, "SPY")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live_paper_control (control_id, armed, updated_at) VALUES (1, false, :now) ON CONFLICT DO NOTHING"
            ),
            {"now": datetime.now(UTC)},
        )

    runtime.execution_ready = True
    await runtime._process_pending()
    assert len(fake_broker.orders_submitted) == 0


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_market_closed_no_post(fake_broker, market):
    _, engine, _, _ = market
    fake_broker.is_open = False
    runtime = LivePaperExecutionRuntime(fake_broker, engine, "SPY")
    runtime.execution_ready = True
    await runtime._process_pending()
    assert len(fake_broker.orders_submitted) == 0





@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_live_paper_buy_e2e_real_db(fake_broker, market):
    # Setup
    _, engine, _, _ = market
    symbol = "AAPL"

    # 1. Clean DB tables we need
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM broker_fills"))
        conn.execute(text("DELETE FROM broker_orders"))
        conn.execute(text("DELETE FROM risk_decisions"))
        conn.execute(text("DELETE FROM signals"))
        conn.execute(text("DELETE FROM candles"))
        conn.execute(text("DELETE FROM live_paper_control"))

    # 2. Insert market data (1m recent candle so it's not stale)
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live_paper_control (control_id, armed, activation_cutoff, updated_at) VALUES (1, true, :c, :n)"
            ),
            {"c": cutoff, "n": now},
        )
        candle_id = uuid4()
        conn.execute(
            text(
                "INSERT INTO candles (candle_id, symbol, timeframe, provider, open_time, close_time, open, high, low, close, volume, is_closed) VALUES (:cid, :sym, '15m', 'alpaca', :ot, :ct, 150, 155, 149, 150, 1000, true)"
            ),
            {"cid": candle_id, "sym": symbol, "ot": now - timedelta(minutes=15), "ct": now},
        )
        # Also need a 1m candle so it's not stale
        conn.execute(
            text(
                "INSERT INTO candles (candle_id, symbol, timeframe, provider, open_time, close_time, open, high, low, close, volume, is_closed) VALUES (:cid, :sym, '1m', 'alpaca', :ot, :ct, 150, 155, 149, 150, 1000, true)"
            ),
            {"cid": uuid4(), "sym": symbol, "ot": now - timedelta(minutes=1), "ct": now},
        )

        signal_id = uuid4()
        conn.execute(
            text(
                "INSERT INTO signals (signal_id, candle_id, strategy_version, signal_type, generated_at) VALUES (:sid, :cid, 'v2-15m-baseline', 'BUY', :now)"
            ),
            {"sid": signal_id, "cid": candle_id, "now": now},
        )

        decision_id = uuid4()
        conn.execute(
            text(
                "INSERT INTO risk_decisions (decision_id, signal_id, decision, reason, decided_at) VALUES (:did, :sid, 'APPROVED', 'ok', :now)"
            ),
            {"did": decision_id, "sid": signal_id, "now": now},
        )

    class FakeProvider:
        def get_status(self):
            class Status:
                state = "connected"

            return Status()

    from services.api.live_paper_runtime import LivePaperExecutionRuntime

    runtime = LivePaperExecutionRuntime(fake_broker, engine, [symbol], FakeProvider())
    runtime.execution_ready = True

    # Execute process_pending
    await runtime._process_pending()

    # Verify order submitted exactly once
    assert len(fake_broker.orders_submitted) == 1
    sym, side, qty, cid = fake_broker.orders_submitted[0]
    assert sym == symbol
    assert side == "BUY"
    assert qty == 6  # 10% of 10000 equity = 1000. 1000 / 150 = 6.66 -> 6

    # Verify DB persistence
    with engine.begin() as conn:
        orders = conn.execute(
            text("SELECT status, requested_qty FROM broker_orders WHERE client_order_id = :cid"),
            {"cid": cid},
        ).fetchall()
        assert len(orders) == 1
        assert orders[0].status == "accepted"
        assert orders[0].requested_qty == 6

    # Test reconciliation partial fill delta
    fake_broker.orders_submitted.clear()

    # Simulate a fill of 2 shares on broker side
    r_order = fake_broker.submit_order(symbol, "BUY", 6, cid)
    r_order.status = "partially_filled"
    r_order.filled_qty = 2
    r_order.filled_avg_price = Decimal("150")
    # Replace FakeExternalBroker's get_orders response
    fake_broker.get_orders = lambda: [r_order]

    await runtime._reconcile()

    with engine.begin() as conn:
        fills = conn.execute(
            text("SELECT qty FROM broker_fills WHERE client_order_id = :cid"), {"cid": cid}
        ).fetchall()
        assert len(fills) == 1
        assert fills[0].qty == 2

    # Simulate remaining 4 shares filled on broker side (cumulative = 6)
    r_order.status = "filled"
    r_order.filled_qty = 6

    await runtime._reconcile()

    with engine.begin() as conn:
        fills = conn.execute(
            text(
                "SELECT qty FROM broker_fills WHERE client_order_id = :cid ORDER BY filled_at ASC"
            ),
            {"cid": cid},
        ).fetchall()
        assert len(fills) == 2
        assert fills[0].qty == 2
        assert fills[1].qty == 4  # The delta!
