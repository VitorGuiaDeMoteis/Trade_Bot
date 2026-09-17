"""Executar explicitamente no PostgreSQL descartavel da porta 55432."""

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
        "POSTGRES_PORT": "55432",
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
            "observer_analysis_runs",
            "candles",
            "system_events",
            "signals",
            "risk_decisions",
            "legacy_market_archive",
            "paper_runs",
            "paper_events",
            "paper_marks",
            "portfolio_snapshots",
            "positions",
            "system_controls",
            "paper_orders",
            "paper_fills",
            "paper_outcomes",
            "broker_orders",
            "broker_fills",
            "broker_portfolio_snapshots",
            "broker_positions",
        }
        
        # CENÁRIO B - Banco contendo Paper data
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO paper_runs (run_id, mode, provider, status, initial_cash, cash, step, fee_bps, slippage_bps, fees, realized_pnl, dataset, dataset_hash, created_at) VALUES ('00000000-0000-0000-0000-000000000000', 'REPLAY', 'alpaca', 'RUNNING', 100, 100, 1, 0, 0, 0, 0, '{}', 'hash', now()) ON CONFLICT DO NOTHING"))
            
        with pytest.raises(Exception) as excinfo:
            command.downgrade(config, "base")
        assert "paper_data_present" in str(excinfo.value)
        
        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM paper_runs")).scalar()
            assert count >= 1
            
        # CENÁRIO A - Banco de teste vazio
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE paper_runs, candles CASCADE"))

            
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

