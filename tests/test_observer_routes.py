import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_market_integration import market as market
from test_observer import raw_snapshot
from test_observer_database import audit as audit

from services.api.main import create_app
from services.api.models import observer_analysis_runs
from services.api.observer_store import analyze
from services.observer.provider import FakeProvider
from services.observer.snapshot import project

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


@pytest.fixture
def client(market, audit):
    assert market[0].postgres_port == 5433 and market[0].postgres_db == "trading_bot_test"
    with TestClient(create_app(market[0].model_copy(update={"simulator_enabled": False}))) as value:
        yield value


def test_observer_routes(client, audit):
    assert client.get("/api/v1/observer/status").json()["status"] == "DISABLED"
    assert client.get("/api/v1/observer/analyses").json() == []
    assert client.get(f"/api/v1/observer/analyses/{uuid4()}").status_code == 404
    assert client.get("/api/v1/observer/analyses/invalid-uuid").status_code == 422
    ident = uuid4()
    result = analyze(audit, ident, project(raw_snapshot()), FakeProvider(), enabled=True)
    status = client.get("/api/v1/observer/status").json()
    assert status["status"] == "OK" and status["latency_ms"] == result["latency_ms"]
    items = client.get("/api/v1/observer/analyses").json()
    assert len(items) == 1 and items[0]["analysis_id"] == str(ident)
    assert items[0]["regime"] == "UNCERTAIN" and items[0]["confidence"] == 0
    detail = client.get(f"/api/v1/observer/analyses/{ident}").json()
    assert detail["validated_output"] == result["validated_output"]
    assert "sanitized_input" not in detail and "request_hash" not in detail
    for path in ["status", "analyses", f"analyses/{ident}"]:
        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            assert client.request(method, f"/api/v1/observer/{path}").status_code == 405


@pytest.mark.parametrize(
    "field,value",
    [
        ("validated_output", {"raw_stdout": "PLANTED_PRIVATE_SECRET"}),
        ("model", "C:/private/.env"),
        ("error_code", "password=PLANTED_PRIVATE"),
    ],
)
def test_corrupt_audit_never_exposes_unvalidated_content(client, audit, field, value):
    ident = uuid4()
    # DEGRADED allows a controlled error_code without violating the table check.
    result = analyze(
        audit, ident, project(raw_snapshot()), FakeProvider(), enabled=field != "error_code"
    )
    if field == "validated_output":
        value = {**result["validated_output"], **value}
    with audit.begin() as c:
        c.execute(observer_analysis_runs.update().values(**{field: value}))
    for path in ["status", "analyses", f"analyses/{ident}"]:
        response = client.get(f"/api/v1/observer/{path}")
        assert response.status_code == 503
        assert "PLANTED" not in response.text and "private" not in response.text


def test_disabled_reason_is_available_without_changing_audit_status(client, audit):
    ident = uuid4()
    analyze(audit, ident, project(raw_snapshot()), FakeProvider())
    item = client.get("/api/v1/observer/analyses").json()[0]
    assert item["status"] == "DEGRADED" and item["error_code"] == "DISABLED"
