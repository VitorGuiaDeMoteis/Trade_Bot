import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from packages.contracts.broker import BrokerAccount, BrokerOrder, BrokerPosition, ExternalBroker
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

    async def get_clock(self):
        return {"is_open": self.is_open, "timestamp": datetime.now(UTC).isoformat()}


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
