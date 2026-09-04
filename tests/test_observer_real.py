import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_observer import raw_snapshot

from packages.contracts.observer import MAX_OUTPUT_BYTES, parse_output
from packages.contracts.observer_real import REAL_MODEL, REAL_TIMEOUT, WEIGHTS_HASH
from services.observer.engine import evaluate
from services.observer.isolated import IsolatedProvider
from services.observer.prompt import PROMPT
from services.observer.provider import FakeProvider
from services.observer.real import RealIsolatedProvider
from services.observer.snapshot import project

spec = importlib.util.spec_from_file_location(
    "real_worker", "infrastructure/observer_real/worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def valid_output():
    return json.loads(asyncio.run(FakeProvider().generate(b"", "")))


def envelope(content=None):
    return {
        "model": REAL_MODEL,
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 100,
        "eval_count": 90,
        "message": {"content": json.dumps(valid_output()) if content is None else content},
    }


def test_fixed_request_no_tools_or_inherited_configuration(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "OLLAMA_HOST", "ALPACA_API_KEY_ID"):
        monkeypatch.setenv(key, "PLANTED_PRIVATE")
    snapshot = project(raw_snapshot()).payload()
    data = worker.payload(snapshot, PROMPT, {"type": "object"})
    assert data["messages"] == [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": snapshot.decode()},
    ]
    assert "PLANTED" not in json.dumps(data) and "tools" not in data
    assert data["model"] == REAL_MODEL and data["stream"] is False and data["think"] is False
    assert data["options"]["temperature"] == 0
    assert data["options"]["num_ctx"] == 16384 and data["options"]["num_predict"] == 1024


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "http://remote.invalid"),
        ("GET", "http://192.168.1.2:11434/api/tags"),
        ("POST", "/api/pull"),
        ("POST", "http://0.0.0.0:11434/api/chat"),
    ],
)
def test_no_arbitrary_endpoint_or_pull(method, path):
    with pytest.raises(ValueError):
        worker.request(method, path)


@pytest.mark.parametrize(
    "failure", ["timeout", "refused", "redirect", "http", "invalid", "truncated", "large"]
)
def test_transport_failures_and_proxy_ignored(monkeypatch, failure):
    monkeypatch.setenv("HTTP_PROXY", "http://remote.invalid")

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 11434, worker.TIMEOUT)

        def request(self, method, path, **kwargs):
            if failure == "timeout":
                raise TimeoutError()
            if failure == "refused":
                raise ConnectionRefusedError()

        def getresponse(self):
            return self

        @property
        def status(self):
            return 302 if failure == "redirect" else 503 if failure == "http" else 200

        def read(self, count):
            assert count == worker.MAX_ENVELOPE + 1
            return (
                b"x" * count
                if failure == "large"
                else b'{"a":'
                if failure == "truncated"
                else b"invalid"
            )

        def close(self):
            pass

    monkeypatch.setattr(worker.http.client, "HTTPConnection", Connection)
    with pytest.raises((ValueError, OSError)):
        worker.request("POST", "/api/chat", {})


def test_reasoning_field_is_discarded_but_content_is_never_repaired():
    value = envelope()
    value["message"]["thinking"] = "PLANTED reasoning"
    raw = worker.extract(value)
    assert b"PLANTED" not in raw
    assert parse_output(raw).regime.label == "UNCERTAIN"


@pytest.mark.parametrize(
    "text",
    [
        "text {}",
        "{} text",
        "<think>secret</think>{}",
        '{"a":1,"a":2}',
        '{"a":',
        "NaN",
        "[]",
        "x" * (MAX_OUTPUT_BYTES + 1),
    ],
)
def test_reject_raw_reasoning_extra_truncated_or_large_content(text):
    with pytest.raises(ValueError):
        worker.extract(envelope(text))


@pytest.mark.parametrize(
    "field,value",
    [
        ("done", False),
        ("done_reason", "length"),
        ("model", "other-model"),
        ("prompt_eval_count", 16383),
        ("eval_count", 1025),
    ],
)
def test_incomplete_wrong_model_or_context_truncation_rejected(field, value):
    result = envelope()
    result[field] = value
    with pytest.raises(ValueError):
        worker.extract(result)


@pytest.mark.parametrize(
    "case", ["buy", "sell", "order", "url", "path", "confidence", "enum", "tool"]
)
def test_runtime_json_mode_does_not_replace_host_contract(case):
    result = copy.deepcopy(valid_output())
    if case in ("buy", "sell", "url", "path"):
        result["observations"] = [
            {"buy": "BUY", "sell": "SELL", "url": "https://bad.invalid", "path": "C:/private/.env"}[
                case
            ]
        ]
    elif case == "order":
        result["order"] = {}
    elif case == "confidence":
        result["regime"]["confidence"] = 1.1
    elif case == "enum":
        result["regime"]["label"] = "BULL"
    item = envelope(json.dumps(result))
    if case == "tool":
        item["message"]["tool_calls"] = [{"name": "execute"}]
    with pytest.raises(ValueError):
        parse_output(worker.extract(item))


def test_real_profile_does_not_change_fake_limits():
    image = "sha256:" + "a" * 64
    fake = IsolatedProvider(Path("docker").resolve(), image)
    real = RealIsolatedProvider(Path("docker").resolve(), image)
    assert "--memory=128m" in fake.arguments("test") and "--cpus=1" in fake.arguments("test")
    args = real.arguments("test")
    for flag in (
        "--memory=7g",
        "--memory-swap=7g",
        "--cpus=6",
        "--pids-limit=128",
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
    ):
        assert flag in args
    assert not any(x.startswith(("--volume", "--mount", "--publish", "--gpus")) for x in args)
    assert real.identity.model_version == "sha256:" + WEIGHTS_HASH
    assert real.identity.image_digest == image


def test_real_internal_timeout_is_not_classified_as_generic_model_error():
    real = RealIsolatedProvider(None, "sha256:" + "a" * 64)
    with pytest.raises(TimeoutError):
        real.check_returncode(124)
    with pytest.raises(RuntimeError):
        IsolatedProvider(None, "sha256:" + "a" * 64).check_returncode(124)
    with pytest.raises(RuntimeError):
        real.check_returncode(1)
    real.check_returncode(0)


def test_gpu_is_explicit_device_zero_with_separate_token_budget():
    real = RealIsolatedProvider(None, "sha256:" + "a" * 64, gpu=True)
    real.docker = Path("docker").resolve()
    args = real.arguments("test")
    assert args[args.index("--gpus") + 1] == "device=0"
    assert "--network=none" in args and "--memory=7g" in args
    snapshot = project(raw_snapshot()).payload()
    assert worker.payload(snapshot, PROMPT, {}, gpu=True)["options"]["num_predict"] == 8192
    assert worker.payload(snapshot, PROMPT, {}, gpu=True)["options"]["num_ctx"] == 32768
    assert worker.payload(snapshot, PROMPT, {}, gpu=True)["think"] is True
    assert worker.payload(snapshot, PROMPT, {}, gpu=False)["options"]["num_predict"] == 1024
    value = envelope()
    value["eval_count"] = 8193
    with pytest.raises(ValueError):
        worker.extract(value, gpu=True)


@pytest.mark.parametrize("case", ["wrong", "large", "missing", "hang"])
def test_image_preflight_is_bounded_and_never_inherits_host_secrets(monkeypatch, case):
    original = asyncio.create_subprocess_exec
    calls = []
    monkeypatch.setenv("POSTGRES_PASSWORD", "PLANTED_PRIVATE")
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.invalid:2375")
    scripts = {
        "wrong": "print('{}')",
        "large": "print('x'*10000)",
        "missing": "raise SystemExit(1)",
        "hang": "import time;time.sleep(60)",
    }

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        assert args[1:3] == ("image", "inspect")
        assert "PLANTED" not in str(kwargs["env"])
        assert "remote.invalid" not in str(kwargs["env"])
        return await original(sys.executable, "-I", "-S", "-c", scripts[case], **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    provider = RealIsolatedProvider(Path(sys.executable), "sha256:" + "a" * 64)
    result = asyncio.run(evaluate(project(raw_snapshot()), provider, enabled=True, timeout=0.5))
    assert result["status"] == "DEGRADED" and result["fallback"] == "HOLD"
    assert len(calls) == 1


def test_real_only_timeout_extension(monkeypatch):
    provider = RealIsolatedProvider(None, "sha256:" + "a" * 64)

    output = json.dumps(valid_output()).encode()

    async def immediate(snapshot, prompt):
        return output

    monkeypatch.setattr(provider, "generate", immediate)
    snapshot = project(raw_snapshot())
    assert asyncio.run(evaluate(snapshot, provider, enabled=True, timeout=31))["status"] == "OK"
    assert (
        asyncio.run(evaluate(snapshot, FakeProvider(), enabled=True, timeout=31))["error_code"]
        == "INVALID_TIMEOUT"
    )
    assert (
        asyncio.run(evaluate(snapshot, provider, enabled=True, timeout=REAL_TIMEOUT + 1))[
            "error_code"
        ]
        == "INVALID_TIMEOUT"
    )
