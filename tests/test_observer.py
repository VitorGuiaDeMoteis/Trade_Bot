import ast
import asyncio
import copy
import json
from pathlib import Path

import pytest

from packages.contracts.observer import (
    MAX_OUTPUT_BYTES,
    AIObserverOutput,
    AIObserverSnapshot,
    canonical,
)
from services.observer.engine import evaluate
from services.observer.isolated import IsolatedProvider
from services.observer.prompt import PROMPT
from services.observer.provider import FakeProvider
from services.observer.snapshot import project


def raw_snapshot():
    return {
        "as_of_utc": "2026-09-03T14:00:00Z",
        "provider": "alpaca",
        "session_state": "connected",
        "symbols": ["SPY"],
        "timeframe": "1h",
        "candles": [
            {
                "symbol": "SPY",
                "open_time": "2026-09-03T13:00:00Z",
                "close_time": "2026-09-03T14:00:00Z",
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": 12,
                "is_closed": True,
            }
        ],
        "signals": [
            {
                "symbol": "SPY",
                "generated_at": "2026-09-03T14:00:00Z",
                "strategy_version": "v1-deterministic",
                "signal_type": "BUY",
            }
        ],
        "risk_decisions": [
            {
                "symbol": "SPY",
                "decided_at": "2026-09-03T14:00:00Z",
                "decision": "APPROVED",
            }
        ],
        "paper": None,
        "accepted_backtest": None,
    }


def valid_output():
    return json.loads(asyncio.run(FakeProvider().generate(b"{}", PROMPT)))


class BadProvider(FakeProvider):
    def __init__(self, payload):
        self.payload = payload

    async def generate(self, snapshot, prompt):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_fake_ok_and_deterministic_snapshot():
    raw = raw_snapshot()
    snapshot = project(raw)
    assert (
        snapshot.payload() == AIObserverSnapshot.model_validate_json(snapshot.payload()).payload()
    )
    first = asyncio.run(evaluate(snapshot, FakeProvider(), enabled=True))
    second = asyncio.run(evaluate(snapshot, FakeProvider(), enabled=True))
    assert first["status"] == "OK" and first["fallback"] is None
    assert first["output_hash"] == second["output_hash"]
    assert first["input_hash"] == snapshot.input_hash
    assert first["prompt_version"] == "observer-v1" and first["model_version"] == "1"


def test_explicit_projection_excludes_secrets_at_every_source_boundary():
    raw = raw_snapshot()
    secret = "PLANTED_DO_NOT_FORWARD_78321"
    raw.update(
        config={"ALPACA_API_KEY_ID": secret, "POSTGRES_PASSWORD": secret, "database_url": secret},
        token=secret,
        account_id=secret,
        path=secret,
    )
    for group in ("candles", "signals", "risk_decisions"):
        raw[group][0].update(reason=secret, token=secret, database_url=secret)
    value = project(raw)
    assert secret.encode() not in value.payload()
    assert value.input_hash == project(raw_snapshot()).input_hash
    raw["signals"][0]["strategy_version"] = secret
    with pytest.raises(ValueError):
        project(raw)


@pytest.mark.parametrize(
    "damage",
    [
        "json",
        "truncated",
        "prefix",
        "suffix",
        "extra",
        "enum",
        "confidence",
        "giant",
        "order",
        "buy",
        "unicode",
        "secret",
        "duplicate",
    ],
)
def test_adversarial_model_output_is_degraded_without_raw_data(damage):
    output = valid_output()
    if damage == "extra":
        output["unknown"] = "x"
    if damage == "enum":
        output["regime"]["label"] = "PROFIT"
    if damage == "confidence":
        output["regime"]["confidence"] = 1.01
    if damage == "order":
        output["order"] = {"side": "BUY", "quantity": 10}
    if damage == "buy":
        output["observations"] = ["BUY agora"]
    if damage == "unicode":
        output["observations"] = ["texto\u202emalicioso"]
    if damage == "secret":
        output["observations"] = ["password=PLANTED_DO_NOT_FORWARD"]
    payload = canonical(output)
    payload = {
        "json": b"not json",
        "truncated": payload[:-3],
        "prefix": b"hello" + payload,
        "suffix": payload + b"thanks",
        "giant": b"x" * (MAX_OUTPUT_BYTES + 1),
        "duplicate": b'{"schema_version":"1.0","schema_version":"1.0"}',
    }.get(damage, payload)
    result = asyncio.run(evaluate(project(raw_snapshot()), BadProvider(payload), enabled=True))
    assert result["status"] == "DEGRADED" and result["fallback"] == "HOLD"
    assert result["validated_output"] is None and result["output_hash"] is None
    assert "PLANTED_DO_NOT_FORWARD" not in str(result)


@pytest.mark.parametrize(
    "problem,expected",
    [
        ("empty", "NO_CANDLES"),
        ("stale", "STALE_DATA"),
        ("degraded", "PROVIDER_DEGRADED"),
        ("disabled", "DISABLED"),
        ("invalid", "INVALID_SNAPSHOT"),
    ],
)
def test_unusable_inputs_never_invoke_model(problem, expected):
    raw = raw_snapshot()
    if problem == "empty":
        raw["candles"] = []
    if problem == "stale":
        raw["as_of_utc"] = "2026-09-04T14:00:00Z"
    if problem == "degraded":
        raw["session_state"] = "degraded"
    result = asyncio.run(
        evaluate(
            None if problem == "invalid" else project(raw),
            BadProvider(AssertionError("not called")),
            enabled=problem != "disabled",
        )
    )
    assert result["error_code"] == expected and result["fallback"] == "HOLD"


def test_timeout_missing_process_and_exception_are_redacted():
    class Slow(FakeProvider):
        async def generate(self, snapshot, prompt):
            await asyncio.sleep(10)
            return b"{}"

    assert (
        asyncio.run(evaluate(project(raw_snapshot()), Slow(), enabled=True, timeout=0.02))[
            "error_code"
        ]
        == "TIMEOUT"
    )
    for error, code in [
        (FileNotFoundError("private-path-secret"), "MODEL_UNAVAILABLE"),
        (RuntimeError("password=private-secret"), "MODEL_ERROR"),
    ]:
        result = asyncio.run(evaluate(project(raw_snapshot()), BadProvider(error), enabled=True))
        assert result["error_code"] == code and "private" not in str(result)


@pytest.mark.parametrize(
    "damage", ["giant", "future", "partial", "float", "unknown", "control", "too_many_symbols"]
)
def test_invalid_snapshots_fail_closed(damage):
    raw = raw_snapshot()
    if damage == "giant":
        raw["candles"] *= 1000
    if damage == "future":
        raw["as_of_utc"] = "2026-09-03T13:30:00Z"
    if damage == "partial":
        raw["candles"][0]["is_closed"] = False
    if damage == "float":
        raw["candles"][0]["open"] = 100.0
    if damage == "unknown":
        raw["session_state"] = "https://execution"
    if damage == "control":
        raw["symbols"] = ["SPY\u0000"]
    if damage == "too_many_symbols":
        raw["symbols"] = list("ABCDE")
    with pytest.raises(ValueError):
        project(raw)


def test_canonical_cross_asset_order_and_size_bound():
    raw = raw_snapshot()
    other = copy.deepcopy(raw["candles"][0])
    other["symbol"] = "AAPL"
    raw["candles"].append(other)
    raw["symbols"] = ["SPY", "AAPL"]
    first = project(raw)
    raw["candles"].reverse()
    raw["symbols"].reverse()
    assert first.input_hash == project(raw).input_hash
    assert len(first.payload()) < 65536


def test_observer_import_and_call_boundaries():
    forbidden = {"PaperExecutor", "submit_order", "TradingClient", "set_paused", "resume", "reset"}
    paths = [
        *Path("services/observer").glob("*.py"),
        Path("services/api/observer_source.py"),
        Path("services/api/observer_store.py"),
    ]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Name, ast.Attribute)):
                assert (node.id if isinstance(node, ast.Name) else node.attr) not in forbidden
            if isinstance(node, ast.ImportFrom):
                assert all(a.name not in forbidden for a in node.names)
                if path.parent == Path("services/observer"):
                    assert not (node.module or "").startswith(
                        (
                            "services.api",
                            "services.paper_executor",
                            "services.risk_engine",
                            "services.strategy_engine",
                            "services.backtesting",
                            "sqlalchemy",
                        )
                    )
    assert "os.environ" not in Path("services/observer/engine.py").read_text()


def test_oci_arguments_no_mounts_credentials_or_network():
    provider = IsolatedProvider(Path("docker.exe").resolve(), "sha256:" + "a" * 64)
    args = provider.arguments("observer-test")
    assert "--network=none" in args and "--read-only" in args
    assert "--user=65534:65534" in args and "--security-opt=no-new-privileges" in args
    assert "--cap-drop=ALL" in args and "--memory=128m" in args
    assert not any(a.startswith(("--volume", "--mount")) for a in args)
    assert [a for a in args if a.startswith("--env")] == ["--env=LANG=C.UTF-8", "--env=TZ=UTC"]


def test_published_schemas_and_embedded_prompt_match_runtime_contracts():
    for name, model in [("input", AIObserverSnapshot), ("output", AIObserverOutput)]:
        published = json.loads(Path(f"docs/contracts/observer-{name}.schema.json").read_text())
        assert published == model.model_json_schema()
        assert published["additionalProperties"] is False
    assert Path("infrastructure/observer/prompt.txt").read_text(encoding="utf-8") == PROMPT


def test_observer_database_configuration_excludes_market_credentials(monkeypatch):
    from services.api.observer_database import ObserverDatabaseSettings

    monkeypatch.setenv("ALPACA_API_KEY_ID", "PLANTED_PRIVATE_KEY")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "PLANTED_PRIVATE_SECRET")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "invalid_provider_for_global_settings")
    config = ObserverDatabaseSettings(_env_file=None, postgres_password="test_only")
    assert set(type(config).model_fields) == {
        "postgres_host",
        "postgres_port",
        "postgres_db",
        "postgres_user",
        "postgres_password",
    }
    assert "PLANTED" not in config.model_dump_json()
