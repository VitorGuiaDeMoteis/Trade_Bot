import os

import pytest
from fastapi.testclient import TestClient
from test_live_paper_runtime import FakeExternalBroker, FakeProvider, seed_eligible
from test_market_integration import market as market

from services.api.live_paper_runtime import LivePaperExecutionRuntime
from services.api.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


@pytest.mark.anyio
async def test_live_paper_dashboard_orders_and_fills_use_postgres(market):
    settings, engine, _, _ = market
    seed_eligible(engine)
    broker = FakeExternalBroker()
    runtime = LivePaperExecutionRuntime(broker, engine, ["SPY"], FakeProvider())
    runtime.execution_ready = True
    await runtime._process_pending()
    broker.orders_remote[0].status = "filled"
    broker.orders_remote[0].filled_qty = broker.orders_remote[0].requested_qty
    broker.orders_remote[0].filled_avg_price = 100
    await runtime._reconcile()

    with TestClient(create_app(settings)) as client:
        dashboard = client.get("/api/v1/live-paper/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["latest_decision"]["signal_type"] == "BUY"
        assert dashboard.json()["account"] == {
            "currency": "USD",
            "equity": None,
            "cash": None,
            "buying_power": None,
            "day_pnl": None,
            "total_pnl": None,
        }
        orders = client.get("/api/v1/live-paper/orders")
        fills = client.get("/api/v1/live-paper/fills")
        assert orders.status_code == fills.status_code == 200
        assert len(orders.json()["items"]) == len(fills.json()["items"]) == 1
        assert orders.json()["items"][0]["status"] == "filled"


def test_fills_database_error_is_sanitized(market):
    settings, _, _, _ = market
    with TestClient(create_app(settings)) as client:

        class BrokenDatabase:
            def begin(self):
                raise RuntimeError("postgresql://user:secret@host/db")

        client.app.state.database = BrokenDatabase()
        response = client.get("/api/v1/live-paper/fills")
        assert response.status_code == 503
        assert response.json() == {"detail": "database_unavailable"}
        assert "secret" not in response.text
