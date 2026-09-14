import asyncio
import subprocess
from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_UP, localcontext
from decimal import Decimal as D
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_backtest import dataset

from packages.domain.backtest import Dataset, encode
from packages.domain.paper import PaperConfig
from services.backtesting.artifacts import load_manifest
from services.backtesting.engine import replay_steps, run
from services.paper_executor.engine import PaperExecutor
from services.replay.app import DEFAULT_DATASET, create_replay_app
from services.replay.runtime import ReplayRuntime
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy


def finish(runtime):
    for _ in range(runtime.total + 1):
        runtime.advance()
    assert runtime.status == "COMPLETED"
    return runtime.report


def test_frozen_history_matches_original_m4_byte_for_byte():
    data, config = load_manifest(DEFAULT_DATASET)
    assert len(data.candles) == 200
    assert {c.symbol for c in data.candles} == {"SPY"}
    expected = run(data, config)
    assert expected["result_hash"] == (
        "b4655eceb8b776dbdfc9fd5f50bb5536eaea3561e19b922355ee49ef540c1461"
    )
    for speed in (0.5, 1, 5, 20):
        runtime = ReplayRuntime(data, config, speed=speed)
        assert encode(finish(runtime)) == encode(expected)
        final = runtime.snapshot()
        assert final["fills_count"] == expected["metrics"]["fills"] == 94
        assert final["closed_trades"] == expected["metrics"]["closed_trades"] == 47
        before = runtime.snapshot()
        runtime.advance()
        assert before == runtime.snapshot()


def test_iterator_uses_real_strategy_risk_and_local_executor_incrementally():
    data = dataset([("100", "101"), ("100", "99"), ("110", "110")])
    with (
        patch.object(
            BaseStrategy, "process_candle", autospec=True, side_effect=BaseStrategy.process_candle
        ) as strategy,
        patch.object(
            RiskEngine, "evaluate", autospec=True, side_effect=RiskEngine.evaluate
        ) as risk,
        patch.object(
            PaperExecutor, "execute", autospec=True, side_effect=PaperExecutor.execute
        ) as executor,
    ):
        steps = replay_steps(data)
        first = next(steps)
        assert first["signals"][0]["signal_type"] == "BUY"
        assert strategy.call_count == 1
        assert risk.call_count == executor.call_count == 0
        second = next(steps)
        assert strategy.call_count == 2
        assert risk.call_count == executor.call_count == 1
        outcome = second["outcomes"][0]
        assert outcome["risk"]["decision"] == "APPROVED"
        assert outcome["status"] == "FILLED"
        assert outcome["quantity"] == 9
        assert outcome["signal"]["generated_at"] <= outcome["executed_at"]
        assert outcome["signal"]["candle_id"] == first["candles"][0]["candle_id"]
        steps.close()


def test_expired_signal_is_blocked_by_real_risk_not_executed():
    bars = dataset([("100", "101"), ("100", "100")]).candles
    data = Dataset(
        (
            bars[0],
            replace(
                bars[1],
                open_time=bars[1].open_time + timedelta(days=1),
                close_time=bars[1].close_time + timedelta(days=1),
            ),
        )
    )
    runtime = ReplayRuntime(data, PaperConfig())
    with patch.object(PaperExecutor, "execute", side_effect=AssertionError("must not execute")):
        finish(runtime)
    assert runtime.snapshot()["fills_count"] == 0
    assert any(e["kind"] == "RISK" and "BLOCKED" in e["text"] for e in runtime.events)


def test_hold_and_empty_dataset_finish_without_fake_orders():
    for data in (Dataset(()), dataset([("100", "100"), ("100", "100")])):
        runtime = ReplayRuntime(data, PaperConfig())
        finish(runtime)
        state = runtime.snapshot()
        assert state["status"] == "COMPLETED" and state["fills_count"] == 0
        assert D(state["portfolio"]["equity"]) == 10000
        if data.candles:
            assert any(e["kind"] == "STRATEGY" and "HOLD" in e["text"] for e in state["events"])


def test_step_snapshots_are_detached_and_decimal_context_is_not_leaked():
    data = dataset([("100", "101"), ("100", "99"), ("110", "110")])
    expected = list(replay_steps(data))
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 12, ROUND_UP
        steps = replay_steps(data)
        first = next(steps)
        assert ctx.prec == 12 and ctx.rounding == ROUND_UP
        first["portfolio"]["cash"] = "1"
        assert list(steps) == expected[1:]
        assert ctx.prec == 12 and ctx.rounding == ROUND_UP


def test_read_only_routes_events_and_reload_never_advance_execution():
    app = create_replay_app(dataset([("100", "101"), ("100", "99")]), autostart=False)
    with TestClient(app) as client:
        runtime = app.state.replay
        runtime.advance()
        before = runtime.snapshot()
        page = client.get("/mission-control")
        assert 'data-mode="replay"' in page.text
        assert "REPLAY LIVE — SIMULAÇÃO HISTÓRICA" in page.text
        assert "READ ONLY — SEM AUTORIDADE DE EXECUÇÃO" in page.text
        assert page.headers["cache-control"] == "no-store"
        for _ in range(3):
            assert client.get("/mission-control").status_code == 200
            assert client.get("/api/v1/replay/state").json() == before
        assert runtime.snapshot() == before
        assert (
            client.get("/api/v1/replay/state?after=" + str(before["last_sequence"])).json()[
                "events"
            ]
            == []
        )
        runtime.advance()
        state = client.get("/api/v1/replay/state?after=" + str(before["last_sequence"])).json()
        assert {e["kind"] for e in state["events"]} >= {
            "CANDLE",
            "STRATEGY",
            "RISK",
            "ORDER",
            "FILL",
            "PORTFOLIO",
        }
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)("/api/v1/replay/state").status_code == 405
        assert client.get("/api/v1/broker/portfolio").status_code == 404
        assert client.post("/api/v1/paper/pause").status_code == 404
        assert client.get("/health").json()["mode"] == "REPLAY"
        assert set(client.get("/openapi.json").json()["paths"]) == {
            "/health",
            "/api/v1/replay/state",
        }


def test_replay_process_needs_no_env_database_network_or_alpaca_imports(tmp_path):
    code = """
import socket, sys
from unittest.mock import patch
from services.replay.app import create_replay_app
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
    app = create_replay_app(autostart=False)
    runtime = app.state.replay
    for _ in range(runtime.total): runtime.advance()
    assert runtime.status == 'COMPLETED'
assert not any(n.startswith(('services.alpaca_paper', 'services.market_data.alpaca',
                             'services.api.main', 'services.api.config')) for n in sys.modules)
print('offline without broker imports')
"""
    import os
    from pathlib import Path

    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ALPACA", "POSTGRES", "EXECUTION_MODE"))
    }
    env["PYTHONPATH"] = str(Path.cwd())
    result = subprocess.run(
        [str(Path(".venv/bin/python").absolute()), "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "offline without broker imports" in result.stdout


@pytest.mark.parametrize("speed", [0, -1, 2, float("inf"), float("nan")])
def test_invalid_speed_rejected(speed):
    with pytest.raises(ValueError):
        ReplayRuntime(Dataset(()), PaperConfig(), speed=speed)


def test_runtime_clock_and_end_do_not_depend_on_browser():
    async def check():
        runtime = ReplayRuntime(dataset([("100", "101"), ("100", "99")]), PaperConfig(), speed=20)
        sleep = asyncio.sleep
        delays = []

        async def fast_sleep(delay):
            delays.append(delay)
            await sleep(0)

        with patch("services.replay.runtime.asyncio.sleep", fast_sleep):
            runtime.start()
            await runtime.task
        assert runtime.status == "COMPLETED" and delays == [0.05]
        before = runtime.snapshot()
        await runtime.stop()
        assert runtime.snapshot() == before

    asyncio.run(check())


def test_buffer_gap_and_isolation_between_runs():
    data, config = load_manifest(DEFAULT_DATASET)
    first, other = ReplayRuntime(data, config), ReplayRuntime(data, config)
    finish(first)
    assert first.snapshot(1)["events_truncated"]
    assert len(first.events) == 400
    assert other.snapshot()["step"] == 0 and other.snapshot()["fills_count"] == 0
    state = first.snapshot()
    state["portfolio"]["cash"] = "0"
    assert first.snapshot()["portfolio"]["cash"] != "0"


def test_error_is_terminal_and_visible():
    async def check():
        app = create_replay_app(Dataset(()), autostart=False)
        runtime = app.state.replay
        with patch.object(runtime, "advance", side_effect=ValueError("bad data")):
            runtime.start()
            await runtime.task
        assert runtime.status == "ERROR"
        assert runtime.snapshot()["events"][-1]["kind"] == "REPLAY"
        await runtime.stop()

    asyncio.run(check())
