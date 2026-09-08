import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from packages.contracts.broker import BrokerAccount, BrokerOrder, BrokerPosition, ExternalBroker
from services.api.live_paper_runtime import LivePaperExecutionRuntime
from services.api.main import create_app


class FakeExternalBroker(ExternalBroker):
    async def get_account(self) -> BrokerAccount:
        return BrokerAccount("USD", Decimal("10000"), Decimal("10000"), Decimal("20000"))

    async def get_positions(self) -> list[BrokerPosition]:
        return []

    async def get_orders(self) -> list[BrokerOrder]:
        return []

    async def get_order_by_client_order_id(self, client_order_id: str):
        return None

    async def submit_order(
        self, symbol: str, side: str, quantity: int, client_order_id: str
    ) -> BrokerOrder:
        return BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id="fake-id",
            symbol=symbol,
            side=side,
            status="submitted",
            requested_qty=quantity,
            filled_qty=0,
            filled_avg_price=Decimal("0"),
            submitted_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def get_clock(self):
        return {"is_open": True, "timestamp": datetime.now(UTC).isoformat()}


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_lifespan_live_paper_reconciliation(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "alpaca_paper")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test")

    app = create_app()

    # We replace the actual broker injected in main with our FakeExternalBroker.
    # But wait, main.py lifespan creates the broker itself.
    # So we'll patch it.

    import services.paper_executor.alpaca

    fake_broker = FakeExternalBroker()
    monkeypatch.setattr(
        services.paper_executor.alpaca, "AlpacaPaperBroker", lambda *a, **kw: fake_broker
    )

    async with app.router.lifespan_context(app):
        runtime = getattr(app.state, "live_paper_runtime", None)
        assert runtime is not None, "Runtime should be instantiated in alpaca_paper mode"
        assert isinstance(runtime, LivePaperExecutionRuntime)

        # Give it a moment to run reconciliation
        await asyncio.sleep(0.5)

        assert runtime.running is True, "Runtime should be started"
        assert runtime.execution_ready is True, (
            "Runtime should be execution_ready after reconciliation"
        )
