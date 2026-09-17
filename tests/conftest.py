"""All automated tests are offline by default; integration uses only localhost."""

import os

import httpx
import pytest

import services.market_data.alpaca_provider as alpaca
from services.api.config import Settings, get_settings

TEST_DATABASE_ENV = {
    "APP_ENV": "test",
    "DATABASE_ROLE": "test",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "55432",
    "POSTGRES_DB": "trading_bot_test",
    "POSTGRES_USER": "test_only",
    "POSTGRES_PASSWORD": "test_only",
    "RUNTIME_POSTGRES_HOST": "127.0.0.1",
    "RUNTIME_POSTGRES_PORT": "5432",
    "RUNTIME_POSTGRES_DB": "trading_bot_dev",
    "TEST_POSTGRES_DB": "trading_bot_test",
}


def pytest_configure(config):
    supplied_database = os.environ.get("POSTGRES_DB")
    supplied_role = os.environ.get("DATABASE_ROLE")
    supplied_url = os.environ.get("DATABASE_URL")
    if (
        supplied_database is not None and supplied_database != TEST_DATABASE_ENV["POSTGRES_DB"]
    ) or (supplied_role is not None and supplied_role != "test"):
        pytest.exit("REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE")
    if supplied_url:
        pytest.exit(
            "REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE: "
            "DATABASE_URL is unsupported; use the explicit test database variables"
        )
    for name, value in TEST_DATABASE_ENV.items():
        os.environ[name] = value
    try:
        Settings(_env_file=None)
    except ValueError as error:
        pytest.exit(f"REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE: {error}")


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch):  # type: ignore
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "simulator")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "")
    monkeypatch.setenv("RUN_ALPACA_SMOKE_TEST", "0")
    original_send = httpx.AsyncClient.send

    async def offline_send(client, *args, **kwargs):  # type: ignore
        if not isinstance(client._transport, httpx.MockTransport):
            pytest.fail("External HTTP forbidden in automated tests; inject MockTransport")
        return await original_send(client, *args, **kwargs)

    def offline_connect(*args, **kwargs):  # type: ignore
        pytest.fail("External WebSocket forbidden in automated tests; inject a fake")

    monkeypatch.setattr(httpx.AsyncClient, "send", offline_send)
    monkeypatch.setattr(alpaca, "connect", offline_connect)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
