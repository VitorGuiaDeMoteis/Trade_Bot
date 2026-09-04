import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_market_integration import market as market
from test_observer import raw_snapshot
from test_observer_database import audit as audit
from test_observer_database import fingerprint
from test_paper_database import seed

from services.api.main import create_app
from services.api.observer_store import analyze
from services.observer.provider import FakeProvider
from services.observer.real import RealIsolatedProvider
from services.observer.snapshot import project

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL"),
]


@pytest.mark.parametrize(
    "case", ["valid", "timeout", "missing", "invalid", "large", "reasoning", "schema"]
)
def test_real_profile_persistence_has_no_financial_effect(market, audit, monkeypatch, case):
    paper = seed(market)
    paper.replay(max_steps=2)
    paper.set_paused(True)
    before = fingerprint(audit)
    provider = RealIsolatedProvider(None, "sha256:" + "a" * 64)

    async def generate(snapshot, prompt):
        if case == "timeout":
            raise TimeoutError()
        if case == "missing":
            raise FileNotFoundError()
        if case == "invalid":
            return b"invalid"
        if case == "large":
            return b"x" * 16385
        if case == "reasoning":
            return b"<think>reason</think>{}"
        if case == "schema":
            return b'{"order":"BUY"}'
        return await FakeProvider().generate(snapshot, prompt)

    monkeypatch.setattr(provider, "generate", generate)
    ident = uuid4()
    snapshot = project(raw_snapshot())
    result = analyze(audit, ident, snapshot, provider, enabled=True, timeout=60)
    assert result["image_digest"] == provider.image and result["provider"] == "oci-local"
    assert result["status"] == ("OK" if case == "valid" else "DEGRADED")
    assert result["fallback"] == (None if case == "valid" else "HOLD")
    assert fingerprint(audit) == before
    assert analyze(audit, ident, snapshot, provider, enabled=True, timeout=60) == result
    other = RealIsolatedProvider(None, "sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="conflict"):
        analyze(audit, ident, snapshot, other, enabled=True, timeout=60)
    different_profile = RealIsolatedProvider(None, provider.image, gpu=True)
    with pytest.raises(ValueError, match="conflict"):
        analyze(audit, ident, snapshot, different_profile, enabled=True, timeout=60)
    with TestClient(
        create_app(market[0].model_copy(update={"simulator_enabled": False}))
    ) as client:
        response = client.get(f"/api/v1/observer/analyses/{ident}")
        assert response.status_code == 200
        body = response.json()
        assert body["image_digest"] == provider.image
        assert "sanitized_input" not in body and "request_hash" not in body
        assert "<think>" not in json.dumps(body)
    assert fingerprint(audit) == before
