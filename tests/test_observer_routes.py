import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings
from services.api.main import create_app
from services.api.models import observer_analysis_runs

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]



@pytest.fixture
def settings():
    return Settings(
        app_env="local",
        postgres_host="127.0.0.1",
        postgres_port=5432,
        postgres_db="trading_bot_dev",
        postgres_user="admin",
        postgres_password="password123",
        alpaca_api_key_id="x",
        alpaca_api_secret_key="y",
        market_data_provider="simulator",
    )


def test_observer_routes(settings):
    # settings and postgres_test fixture ensure database is available
    app = create_app(settings)

    with TestClient(app) as client:
        # Before seeding, status should be DISABLED
        resp = client.get("/api/v1/observer/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "DISABLED"

        # Timeline should be empty
        resp = client.get("/api/v1/observer/analyses")
        assert resp.status_code == 200
        assert resp.json() == []

        # Detail of unknown ID should be 404
        resp = client.get(f"/api/v1/observer/analyses/{uuid4()}")
        assert resp.status_code == 404

        # Detail with invalid UUID
        resp = client.get("/api/v1/observer/analyses/invalid-uuid")
        assert resp.status_code == 422

        # Now seed some fake data via SQLAlchemy directly to the DB
        engine = app.state.database
        with engine.begin() as conn:
            id1 = uuid4()
            conn.execute(
                observer_analysis_runs.insert().values(
                    analysis_id=id1,
                    created_at=datetime.now(UTC),
                    as_of_utc=datetime.now(UTC),
                    provider="simulator",
                    model="fake-model",
                    model_version="1.0",
                    prompt_version="v1",
                    prompt_hash="abc",
                    schema_version="1.0",
                    request_hash="req1",
                    input_hash="in1",
                    output_hash="out1",
                    status="OK",
                    latency_ms=120,
                    sanitized_input={"fake": "input"},
                    validated_output={
                        "schema_version": "1.0",
                        "regime": {"label": "TRENDING", "confidence": 0.8, "evidence": []},
                        "risk_flags": [
                            {"code": "VOLATILITY", "severity": "HIGH", "message": "High vol"}
                        ],
                        "observations": ["fake obs"],
                    },
                )
            )

        # Check status again
        resp = client.get("/api/v1/observer/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "OK"
        assert resp.json()["latency_ms"] == 120

        # Check timeline
        resp = client.get("/api/v1/observer/analyses")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["analysis_id"] == str(id1)
        assert items[0]["regime"] == "TRENDING"
        assert items[0]["confidence"] == 0.8
        assert items[0]["risk_flags_count"] == 1

        # Check detail
        resp = client.get(f"/api/v1/observer/analyses/{id1}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["analysis_id"] == str(id1)
        assert detail["validated_output"]["regime"]["label"] == "TRENDING"
        assert detail["provider"] == "simulator"

        # Verify no POST/PUT/DELETE
        assert client.post("/api/v1/observer/analyses").status_code == 405
        assert client.delete(f"/api/v1/observer/analyses/{id1}").status_code == 405
