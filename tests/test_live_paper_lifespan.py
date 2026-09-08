import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from packages.contracts.broker import (
    BrokerAccount,
    BrokerClock,
    BrokerOrder,
    BrokerPosition,
    ExternalBroker,
)
from services.api.live_paper_runtime import LivePaperExecutionRuntime
from services.api.main import create_app


class FakeExternalBroker(ExternalBroker):
    def __init__(self) -> None:
        self.reconciliation_reads = []

    async def get_account(self) -> BrokerAccount:
        self.reconciliation_reads.append("account")
        return BrokerAccount("USD", Decimal("10000"), Decimal("10000"), Decimal("20000"))

    async def get_positions(self) -> list[BrokerPosition]:
        self.reconciliation_reads.append("positions")
        return []

    async def get_orders(self) -> list[BrokerOrder]:
        self.reconciliation_reads.append("orders")
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

    async def get_clock(self) -> BrokerClock:
        self.reconciliation_reads.append("clock")
        return BrokerClock(is_open=True, timestamp=datetime(2026, 9, 8, 18, 30, tzinfo=UTC))


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required")
@pytest.mark.anyio
async def test_lifespan_live_paper_reconciliation(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "alpaca_paper")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "alpaca")
    monkeypatch.setenv("MARKET_SYMBOLS", "SPY,AAPL,TSLA")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test")

    import services.api.main
    import services.paper_executor.alpaca
    from packages.contracts.market import MarketDataStatus

    fake_broker = FakeExternalBroker()

    class FakeMarketProvider:
        async def get_historical_candles(self, *args, **kwargs):
            return []

        async def subscribe(self):
            await asyncio.sleep(3600)
            yield

        def get_status(self):
            return MarketDataStatus(
                provider="alpaca", state="connected", symbols=["SPY", "AAPL", "TSLA"]
            )

        async def close(self):
            return None

    monkeypatch.setattr(
        services.paper_executor.alpaca, "AlpacaPaperBroker", lambda *a, **kw: fake_broker
    )
    monkeypatch.setattr(
        services.api.main, "AlpacaMarketDataProvider", lambda **kw: FakeMarketProvider()
    )
    app = create_app()

    async with app.router.lifespan_context(app):
        runtime = getattr(app.state, "live_paper", None)
        assert runtime is not None, "Runtime should be instantiated in alpaca_paper mode"
        assert isinstance(runtime, LivePaperExecutionRuntime)

        # Give it a moment to run reconciliation
        await asyncio.sleep(0.5)

        assert runtime.running is True, "Runtime should be started"
        assert runtime.execution_ready is True, (
            "Runtime should be execution_ready after reconciliation"
        )
        assert runtime.symbols == ["SPY", "AAPL", "TSLA"]
        assert set(fake_broker.reconciliation_reads) == {"account", "clock", "positions", "orders"}
    assert runtime._task is None
