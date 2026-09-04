import asyncio
import json
import sys
from pathlib import Path

import pytest
from test_observer import raw_snapshot

from services.observer.engine import evaluate
from services.observer.isolated import IsolatedProvider
from services.observer.prompt import PROMPT
from services.observer.snapshot import project


def fake_runtime(monkeypatch, script):
    original = asyncio.create_subprocess_exec
    calls = []

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        code = script if args[1] == "run" else "pass"
        return await original(sys.executable, "-I", "-S", "-c", code, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    return calls


def test_host_client_environment_allowlist_and_isolated_workdir(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "planted-private-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "planted-db-password")
    monkeypatch.setenv("DOCKER_HOST", "tcp://attacker.invalid:2375")
    calls = fake_runtime(
        monkeypatch,
        "import sys,os,json;sys.stdin.buffer.read();print(json.dumps(dict(os.environ)))",
    )
    provider = IsolatedProvider(Path(sys.executable).resolve(), "sha256:" + "a" * 64)
    result = asyncio.run(provider.generate(project(raw_snapshot()).payload(), PROMPT))
    assert b"planted" not in result and b"attacker" not in result
    env = json.loads(result)
    assert {key.upper() for key in env} <= {
        "SYSTEMROOT",
        "WINDIR",
        "DOCKER_CONFIG",
        "DOCKER_HOST",
        "LC_CTYPE",
    }
    assert calls[0][1]["cwd"] != str(Path.cwd())
    assert not Path(calls[0][1]["cwd"]).exists()
    assert calls[-1][0][1:3] == ("rm", "--force")


@pytest.mark.parametrize(
    "script",
    [
        "import sys;sys.stdin.buffer.read();print('x'*20000)",
        "import sys;sys.stdin.buffer.read();sys.stderr.write('secret'*10000)",
        "import sys,time;sys.stdin.buffer.read();time.sleep(20)",
        "import sys;sys.stdin.buffer.read();sys.stderr.write('password=private');sys.exit(2)",
    ],
)
def test_process_limits_kill_child_discard_stderr_and_cleanup(monkeypatch, script):
    calls = fake_runtime(monkeypatch, script)
    provider = IsolatedProvider(Path(sys.executable).resolve(), "sha256:" + "a" * 64)
    result = asyncio.run(evaluate(project(raw_snapshot()), provider, enabled=True, timeout=0.25))
    assert result["status"] == "DEGRADED" and result["fallback"] == "HOLD"
    assert result["validated_output"] is None and "private" not in str(result)
    assert calls[-1][0][1:3] == ("rm", "--force")


def test_missing_executable_is_safe(tmp_path):
    provider = IsolatedProvider((tmp_path / "absent.exe").resolve(), "sha256:" + "a" * 64)
    result = asyncio.run(evaluate(project(raw_snapshot()), provider, enabled=True))
    assert result["error_code"] == "MODEL_UNAVAILABLE"


def test_uninstalled_runtime_is_safe():
    provider = IsolatedProvider(None, "sha256:" + "a" * 64)
    result = asyncio.run(evaluate(project(raw_snapshot()), provider, enabled=True))
    assert result["error_code"] == "MODEL_UNAVAILABLE" and result["fallback"] == "HOLD"
