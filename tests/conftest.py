"""All automated tests are offline by default; integration uses only localhost."""

import httpx
import pytest

import services.market_data.alpaca_provider as alpaca
from services.api.config import get_settings


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "simulator")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "")
    monkeypatch.setenv("RUN_ALPACA_SMOKE_TEST", "0")
    original_send = httpx.AsyncClient.send

    async def offline_send(client, *args, **kwargs):
        if not isinstance(client._transport, httpx.MockTransport):
            pytest.fail("External HTTP forbidden in automated tests; inject MockTransport")
        return await original_send(client, *args, **kwargs)

    def offline_connect(*args, **kwargs):
        pytest.fail("External WebSocket forbidden in automated tests; inject a fake")

    monkeypatch.setattr(httpx.AsyncClient, "send", offline_send)
    monkeypatch.setattr(alpaca, "connect", offline_connect)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
