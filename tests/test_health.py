import json
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError

from services.api.config import Settings
from services.api.database import SCHEMA_REVISION, check_database
from services.api.main import create_app


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        postgres_password=SecretStr("fake_test_only"),
        simulator_enabled=False,
    )


@pytest.mark.parametrize(
    ("database", "code", "status"),
    [("up", 200, "ok"), ("down", 503, "degraded"), ("schema_pending", 503, "degraded")],
)
def test_health_contract(settings, database, code, status):
    correlation_id = str(uuid4())
    with patch("services.api.main.check_database", return_value=database):
        with TestClient(create_app(settings)) as client:
            client.app.state.simulator.state = "running"
            response = client.get("/health", headers={"X-Correlation-ID": correlation_id})
    assert response.status_code == code
    body = response.json()
    assert body["database"] == database
    assert body["status"] == status
    assert body["mode"] == "SIMULADO"
    assert body["schema_version"] == "1.1"
    assert datetime.fromisoformat(body["checked_at"]).utcoffset().total_seconds() == 0
    assert body["correlation_id"] == response.headers["X-Correlation-ID"] == correlation_id
    assert response.headers["Cache-Control"] == "no-store"
    assert "fake_test_only" not in response.text


def test_invalid_correlation_id_and_log_redaction(settings, caplog):
    with patch("services.api.main.check_database", return_value="down"):
        with TestClient(create_app(settings)) as client, caplog.at_level(logging.INFO):
            response = client.get(
                "/health?token=private_query",
                headers={
                    "X-Correlation-ID": "private_invalid_id",
                    "Authorization": "private_token",
                },
            )
    UUID(response.headers["X-Correlation-ID"])
    records = [r for r in caplog.records if r.name == "trading_bot.api"]
    event = json.loads(records[-1].message)
    assert event["correlation_id"] == response.json()["correlation_id"]
    assert event["status_code"] == 503
    assert "private_" not in records[-1].message


def test_database_failure_returns_down_without_exposing_exception():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("secret_dsn", {}, Exception("password"))
    assert check_database(engine) == "down"


@pytest.mark.parametrize(
    ("table", "revisions", "expected"),
    [
        (None, [], "schema_pending"),
        ("alembic_version", [], "schema_pending"),
        ("alembic_version", ["old"], "schema_pending"),
        ("alembic_version", [SCHEMA_REVISION], "up"),
    ],
)
def test_schema_readiness(table, revisions, expected):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = table
    connection.scalars.return_value.all.return_value = revisions
    assert check_database(engine) == expected


def test_no_control_or_trading_routes(settings):
    with TestClient(create_app(settings)) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/health", "/api/v1/market/candles"}


def test_settings_reject_nonlocal_environment():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", postgres_password=SecretStr("test"))


def test_engine_is_disposed_after_shutdown(settings):
    with patch("services.api.main.create_database_engine") as factory:
        with TestClient(create_app(settings)):
            pass
    factory.return_value.dispose.assert_called_once()


@pytest.mark.parametrize("state", ["starting", "stopped", "degraded", "stalled"])
def test_health_reports_simulator_not_ready(settings, state):
    with patch("services.api.main.check_database", return_value="up"):
        with TestClient(create_app(settings)) as client:
            client.app.state.simulator.state = state
            client.app.state.simulator.provider._state = "offline"
            # mock get_status to return the right state
            with patch.object(client.app.state.simulator.provider, 'get_status', return_value=type('obj', (object,), {'state': state, 'provider': 'simulator', 'feed': 'local', 'symbols': ['TEST'], 'last_persisted_at': None, 'error': None})):
                response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["market_data"]["state"] == state
