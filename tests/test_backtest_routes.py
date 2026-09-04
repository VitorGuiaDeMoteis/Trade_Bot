import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from packages.domain.backtest import Dataset, digest
from services.api.config import Settings
from services.api.main import create_app
from services.backtesting.engine import run


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
    report = run(Dataset(()))
    report.pop("result_hash")
    report["metrics"]["return_pct"] = "1.0"
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


def test_report_resolving_outside_directory_is_not_served(settings, tmp_path, monkeypatch):
    report = run(Dataset(()))
    target = tmp_path / "link.json"
    target.write_text(json.dumps(report))
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        # Model a resolved file symlink without requiring Windows administrator rights.
        return (
            tmp_path.parent / "outside.json" if path == target else original(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "resolve", redirected)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/backtests").json() == []
        for suffix in ("", "/export"):
            assert (
                client.get(f"/api/v1/backtests/{report['result_hash']}{suffix}").status_code == 404
            )


def test_export_serves_validated_snapshot_not_changed_file(settings, tmp_path, monkeypatch):
    from services.api import backtest_routes

    report = run(Dataset(()))
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    original = backtest_routes._load_and_validate_report

    def swap(filepath):
        validated = original(filepath)
        filepath.write_text('{"unvalidated":true}')
        return validated

    monkeypatch.setattr(backtest_routes, "_load_and_validate_report", swap)
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/v1/backtests/{report['result_hash']}/export")
        assert response.status_code == 200
        assert response.json() == report


def test_signed_but_incomplete_report_fails_closed(settings, tmp_path):
    report = {"mode": "BACKTEST", "schema_version": "1.0"}
    report["result_hash"] = digest(report)
    (tmp_path / "incomplete.json").write_text(json.dumps(report))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/backtests").json() == []
        assert client.get(f"/api/v1/backtests/{report['result_hash']}").status_code == 404


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_no_execution_methods(settings, method):
    with TestClient(create_app(settings)) as client:
        for path in ("", "/abc", "/abc/export"):
            assert getattr(client, method)("/api/v1/backtests" + path).status_code == 405


@pytest.mark.parametrize(
    "path", ["/../outside.json", "/%2e%2e%2foutside.json", "/C:%5coutside.json"]
)
def test_traversal_not_served(settings, path):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/backtests" + path).status_code == 404


@pytest.mark.parametrize("damage", ["metric", "frame", "hash", "float"])
def test_invalid_report_contract_fails_closed(settings, tmp_path, damage):
    report = run(Dataset(()))
    report.pop("result_hash")
    if damage == "metric":
        del report["metrics"]["final_equity"]
    elif damage == "frame":
        report["equity_curve"] = [42]
    elif damage == "hash":
        report["dataset_hash"] = "short"
    else:
        report["metrics"]["return_pct"] = 1.0
    report["result_hash"] = digest(report)
    (tmp_path / "invalid.json").write_text(json.dumps(report))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/backtests").json() == []
        for suffix in ("", "/export"):
            assert (
                client.get(f"/api/v1/backtests/{report['result_hash']}{suffix}").status_code == 404
            )
