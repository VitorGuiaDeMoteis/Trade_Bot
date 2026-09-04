"""STOP is local, monotonic and non-secret; never a remote execution capability."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from services.api.config import Settings
from services.api.main import create_app


@pytest.mark.parametrize(
    "peer,host,headers,body,status",
    [
        ("127.0.0.1", "127.0.0.1", {}, b"", 200),
        ("::1", "[::1]", {}, b"", 200),
        ("192.168.1.10", "127.0.0.1", {}, b"", 403),
        ("203.0.113.5", "127.0.0.1", {}, b"", 403),
        ("127.0.0.1", "attacker.example", {}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Origin": "http://127.0.0.1"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Origin": "null"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Origin": ""}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Referer": "http://evil.example"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Sec-Fetch-Site": "same-origin"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"Forwarded": "for=127.0.0.1"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"X-Paper-Control": "resume"}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {"X-Paper-Control": ""}, b"", 403),
        ("127.0.0.1", "127.0.0.1", {}, b'{"paused":false}', 422),
        ("127.0.0.1", "127.0.0.1", {}, b'{"paused":true}', 422),
    ],
)
def test_stop_network_boundary(
    peer: str, host: str, headers: dict[str, str], body: bytes, status: int
) -> None:
    app = create_app()
    app.state.configuration = Settings(_env_file=None, postgres_password=SecretStr("test_only"))
    app.state.database = object()
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=(peer, 55000))
    with patch("services.api.paper_routes.PaperStore") as store:
        response = client.post(
            "/api/v1/paper/pause",
            headers={"Host": f"{host}:8000", "X-Paper-Control": "stop", **headers},
            content=body,
        )
        assert response.status_code == status
        if status == 200:
            store.return_value.set_paused.assert_called_once_with(True)
            assert response.json() == {"paused": True}
            assert response.headers["cache-control"] == "no-store"
        else:
            store.assert_not_called()
    for route in ("resume", "reset", "buy", "sell", "order"):
        assert client.post(f"/api/v1/paper/{route}").status_code == 404
    assert client.options("/api/v1/paper/pause").status_code == 405
    assert client.get("/api/v1/paper/pause").status_code == 405
