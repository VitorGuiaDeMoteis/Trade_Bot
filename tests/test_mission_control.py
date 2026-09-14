import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from scripts.mission_control import create_observation_app
from services.alpaca_paper.observation import ObservationAdapter, ObservationWorker
from services.api.config import Settings
from services.api.main import create_app


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        postgres_password=SecretStr("test"),
        simulator_enabled=False,
        execution_mode="local_paper",
    )


def test_page_served_without_broker_or_database(settings):
    with patch("services.api.main.create_database_engine") as database:
        with TestClient(create_app(settings)) as client:
            response = client.get("/mission-control")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            assert response.headers["cache-control"] == "no-store"
            assert "form-action 'none'" in response.headers["content-security-policy"]
            assert "READ ONLY — SEM AUTORIDADE DE EXECUÇÃO" in response.text
            assert "ALPACA PAPER — DINHEIRO VIRTUAL" in response.text
            assert "get('/health')" in response.text
            assert "get('/api/v1/broker/portfolio')" in response.text
            assert "setTimeout(poll,2000)" in response.text
            assert "/api/v1/paper/portfolio" not in response.text
            assert "<form" not in response.text
            assert client.post("/mission-control").status_code == 405
            assert "/mission-control" not in client.get("/openapi.json").json()["paths"]
        database.return_value.connect.assert_not_called()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_observation_runtime_rejects_mutations(settings, method):
    with TestClient(create_app(settings, observation_only=True)) as client:
        assert getattr(client, method)("/api/v1/paper/pause").status_code == 405
        assert client.get("/mission-control").status_code == 200


def test_demo_factory_selects_observation_worker(settings, monkeypatch):
    monkeypatch.setattr(
        "scripts.mission_control.Settings",
        lambda **kw: settings.model_copy(
            update={
                **kw,
                "alpaca_api_key_id": SecretStr("test"),
                "alpaca_api_secret_key": SecretStr("test"),
            }
        ),
    )
    with (
        patch("services.api.main.ObservationWorker") as observer,
        patch("services.api.main.AlpacaPaperWorker") as trading,
    ):
        observer.return_value.stop = AsyncMock()
        with TestClient(create_observation_app()) as client:
            assert client.app.state.configuration.execution_mode == "alpaca_paper"
            assert isinstance(observer.call_args.args[1], ObservationAdapter)
            observer.return_value.start.assert_called_once()
            trading.assert_not_called()
        observer.return_value.stop.assert_awaited_once()


def test_adapter_allows_only_paper_gets_and_blocks_submit_cancel():
    async def run():
        requests = []

        def handler(request):
            requests.append(request)
            assert request.method == "GET"
            assert request.url.host == "paper-api.alpaca.markets"
            return httpx.Response(200, json={"status": "ACTIVE"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async with ObservationAdapter("test", "test", client) as adapter:
                assert (await adapter.get_account())["status"] == "ACTIVE"
                with pytest.raises(ValueError, match="writes are forbidden"):
                    await adapter.submit_order("SPY", 1, "buy", "never-sent")
                with pytest.raises(ValueError, match="writes are forbidden"):
                    await adapter.cancel_order("never-canceled")
                with pytest.raises(ValueError, match="writes are forbidden"):
                    await adapter._request("PATCH", "/orders/never")
        assert len(requests) == 1

    asyncio.run(run())


@pytest.mark.parametrize("fails", [False, True])
def test_observation_loop_reconciles_without_submitting(settings, fails):
    async def run():
        adapter = AsyncMock(spec=ObservationAdapter)
        worker = ObservationWorker(MagicMock(), adapter, settings)
        worker._process_pending_submits = AsyncMock()
        worker._reconcile_active_orders = AsyncMock(
            side_effect=RuntimeError("test failure") if fails else None
        )
        worker._snapshot_broker_portfolio = AsyncMock()

        async def stop_after_cycle(_):
            worker.running = False

        with patch("services.alpaca_paper.observation.asyncio.sleep", stop_after_cycle):
            worker.start()
            await worker.task
            await worker.stop()
        worker._process_pending_submits.assert_not_awaited()
        worker._reconcile_active_orders.assert_awaited_once()
        assert worker.degraded is fails
        if fails:
            worker._snapshot_broker_portfolio.assert_not_awaited()
        else:
            worker._snapshot_broker_portfolio.assert_awaited_once()
        adapter.__aexit__.assert_awaited_once()

    asyncio.run(run())
