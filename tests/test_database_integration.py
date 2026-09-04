"""Executar explicitamente no PostgreSQL descartavel da porta 5433."""

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import inspect, text

from services.api.config import Settings, get_settings
from services.api.database import SCHEMA_REVISION, create_database_engine
from services.api.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_TESTS") != "1", reason="requer RUN_DB_TESTS=1 e postgres_test"
    ),
]


def test_postgres_migration_round_trip_and_health(monkeypatch):  # type: ignore
    # Conexao fixa ao banco de teste; nunca usa o banco de desenvolvimento.
    values = {
        "APP_ENV": "test",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5433",
        "POSTGRES_DB": "trading_bot_test",
        "POSTGRES_USER": "test_only",
        "POSTGRES_PASSWORD": "test_only",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr("test_only"),
        simulator_enabled=False,
    )
    engine = create_database_engine(settings)
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == SCHEMA_REVISION
            )
            assert connection.scalar(text("SHOW timezone")) == "UTC"
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "candles",
            "system_events",
            "signals",
            "risk_decisions",
            "legacy_market_archive",
        }
        with TestClient(create_app(settings)) as client:
            client.app.state.simulator.state = "connected"  # type: ignore
            assert client.get("/health").status_code == 200
            command.downgrade(config, "base")
            degraded = client.get("/health")
            assert degraded.status_code == 503
            assert degraded.json()["database"] == "schema_pending"
            command.upgrade(config, "head")
            assert client.get("/health").status_code == 200
    finally:
        engine.dispose()
        get_settings.cache_clear()
