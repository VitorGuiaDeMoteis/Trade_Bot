import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from packages.domain.backtest import digest
from services.api.config import Settings
from services.api.main import create_app


@pytest.fixture
def settings(tmp_path: Path):  # type: ignore
    return Settings(
        _env_file=None,
        postgres_password=SecretStr("fake_test_only"),
        backtest_artifacts_dir=str(tmp_path),
        simulator_enabled=False,
    )


def test_list_backtests_empty(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/backtests")
        assert response.status_code == 200
        assert response.json() == []


def test_list_and_get_backtests(settings: Settings, tmp_path: Path) -> None:
    report = {
        "mode": "BACKTEST",
        "schema_version": "1.0",
        "engine_version": "m4-core-v1",
        "strategy_version": "v1",
        "risk_version": "v1",
        "manifest_hash": "abc",
        "dataset_hash": "def",
        "config": {},
        "metrics": {"return_pct": "1.0"},
    }
    result_hash = digest(report)
    report["result_hash"] = result_hash

    (tmp_path / "report.json").write_text(json.dumps(report))

    with TestClient(create_app(settings)) as client:
        # List
        response = client.get("/api/v1/backtests")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["result_hash"] == result_hash
        assert data[0]["metrics"]["return_pct"] == "1.0"

        # Get
        response = client.get(f"/api/v1/backtests/{result_hash}")
        assert response.status_code == 200
        assert response.json()["result_hash"] == result_hash

        # Export
        response = client.get(f"/api/v1/backtests/{result_hash}/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"


def test_invalid_backtests_are_ignored(settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "corrupted.json").write_text("{corrupted")
    (tmp_path / "wrong_hash.json").write_text(
        '{"result_hash": "abc", "mode": "BACKTEST", "schema_version": "1.0"}'
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/backtests")
        assert response.status_code == 200
        assert response.json() == []

        response = client.get("/api/v1/backtests/abc")
        assert response.status_code == 404


def test_missing_backtest(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/backtests/does_not_exist")
        assert response.status_code == 404
