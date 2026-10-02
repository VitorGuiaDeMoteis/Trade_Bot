"""`/health` must not flap in ALPACA PAPER, but the execution gate must stay closed.

`reconcile_once` deliberately closes the execution gate at the top of every
3s cycle (`reconciliation_ready=False`, `degraded=True`,
`degraded_reason="reconciliation_in_progress"`). That is correct for trading --
no order may be placed against half-refreshed broker state -- but it is not a
runtime fault, and `/health` used to read the gate directly, so it returned 503
for part of every cycle in a fully healthy runtime.

Runtime evidence: 14 of 41 observation samples reported
`health.status=degraded` while `paper.degraded=false`, `reconciled=true` and
`paused=false`, every one of them taken 3.06-3.92s after that sample's own
`last_reconciled_at` -- i.e. inside the NEXT cycle's fail-closed window.

These tests pin the split:
- `health_ready()` is the RUNTIME fault signal (a real error, or no verified
  broker picture yet) and stays fail-closed for both cases;
- `reconciliation_ready` / `degraded` remain the EXECUTION gate and are
  untouched, so the in-progress window still submits nothing.

Pure unit tests: stub engine, no Postgres, no broker, no DB mutation.
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from services.alpaca_paper.worker import AlpacaPaperWorker
from services.api.config import Settings
from services.api.main import create_app

IN_PROGRESS = "reconciliation_in_progress"


class _StubEngine:
    """Enough engine for `_enter_degraded`'s snapshot update; no real DB."""

    def __init__(self) -> None:
        self.executed: list[Any] = []

    def begin(self) -> "_StubEngine":
        return self

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        self.executed.append(statement)

    def __enter__(self) -> "_StubEngine":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False


def _worker(engine: _StubEngine | None = None) -> AlpacaPaperWorker:
    return AlpacaPaperWorker(engine or _StubEngine(), None, None)  # type: ignore[arg-type]


def test_startup_is_not_healthy_before_any_reconcile() -> None:
    """No verified broker picture exists yet, so the gate must fail closed."""
    worker = _worker()

    assert worker.degraded is True
    assert worker.has_reconciled is False
    assert worker.degraded_reason == "startup_reconciliation_pending"
    assert worker.health_ready() is False


def test_successful_reconcile_is_healthy() -> None:
    worker = _worker()
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None
    worker.has_reconciled = True

    assert worker.health_ready() is True


def test_cycle_in_progress_stays_healthy_after_a_successful_reconcile() -> None:
    """The regression: this window is not a runtime fault."""
    worker = _worker()
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None
    worker.has_reconciled = True

    worker.reconciliation_ready = False
    worker.degraded = True
    worker.degraded_reason = IN_PROGRESS

    assert worker.health_ready() is True


def test_execution_gate_is_still_closed_while_health_reports_ready() -> None:
    """The safety half of the split: healthy != allowed to trade.

    If a future change ever made these agree, this test fails first.
    """
    worker = _worker()
    worker.has_reconciled = True
    worker.degraded = True
    worker.degraded_reason = IN_PROGRESS

    assert worker.health_ready() is True
    assert worker.reconciliation_ready is False
    assert worker.degraded is True


def test_real_failure_is_unhealthy() -> None:
    """A genuine cycle error still reports DEGRADED (exercises `_enter_degraded`)."""
    worker = _worker()
    worker.has_reconciled = True
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None

    asyncio.run(worker._enter_degraded("alpaca_paper_account_not_active:INACTIVE"))

    assert worker.health_ready() is False
    assert worker.degraded is True
    assert worker.reconciliation_ready is False
    assert worker.has_reconciled is False
    assert worker.degraded_reason == "alpaca_paper_account_not_active:INACTIVE"


def test_in_progress_window_after_a_failure_is_still_unhealthy() -> None:
    """A fault latches `has_reconciled` back to False; it must not self-heal.

    Otherwise the next cycle's `reconciliation_in_progress` sentinel would be
    indistinguishable from the healthy in-progress window and the runtime would
    report OK while still failing every cycle.
    """
    worker = _worker()
    worker.has_reconciled = True
    worker.degraded = False
    worker.reconciliation_ready = True
    worker.degraded_reason = None

    asyncio.run(worker._enter_degraded("observation_reconciliation_failed"))
    worker.degraded_reason = IN_PROGRESS

    assert worker.has_reconciled is False
    assert worker.health_ready() is False


def test_health_endpoint_reports_ok_during_the_fail_closed_window() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        postgres_password=SecretStr("fake_test_only"),
        simulator_enabled=False,
    )
    worker = _worker()
    worker.has_reconciled = True
    worker.degraded = True
    worker.degraded_reason = IN_PROGRESS

    with patch("services.api.main.check_database", return_value="up"):
        with TestClient(create_app(settings, observation_only=True)) as client:
            client.app.state.simulator.state = "connected"  # type: ignore[attr-defined]
            client.app.state.configuration.execution_mode = "alpaca_paper"
            client.app.state.paper_worker = worker  # type: ignore[attr-defined]

            response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "ALPACA PAPER — DINHEIRO VIRTUAL"
    assert datetime.fromisoformat(body["checked_at"]).utcoffset().total_seconds() == 0  # type: ignore
    assert "fake_test_only" not in response.text


def test_health_endpoint_returns_503_for_a_missing_or_failed_worker() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        postgres_password=SecretStr("fake_test_only"),
        simulator_enabled=False,
    )

    with patch("services.api.main.check_database", return_value="up"):
        with TestClient(create_app(settings, observation_only=True)) as client:
            client.app.state.simulator.state = "connected"  # type: ignore[attr-defined]
            client.app.state.configuration.execution_mode = "alpaca_paper"

            client.app.state.paper_worker = None  # type: ignore[attr-defined]
            missing = client.get("/health")

            worker = _worker()
            worker.has_reconciled = True
            asyncio.run(worker._enter_degraded("alpaca_paper_account_not_active:INACTIVE"))
            client.app.state.paper_worker = worker  # type: ignore[attr-defined]
            failed = client.get("/health")

    assert missing.status_code == 503
    assert missing.json()["status"] == "degraded"
    assert failed.status_code == 503
    assert failed.json()["status"] == "degraded"


def test_health_endpoint_reports_503_when_database_is_down_even_if_worker_is_ready() -> None:
    """Health must not be masked by the worker check; database still wins."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        postgres_password=SecretStr("fake_test_only"),
        simulator_enabled=False,
    )
    worker = _worker()
    worker.has_reconciled = True
    worker.degraded = False
    worker.degraded_reason = None

    with patch("services.api.main.check_database", return_value="down"):
        with TestClient(create_app(settings, observation_only=True)) as client:
            client.app.state.simulator.state = "connected"  # type: ignore[attr-defined]
            client.app.state.configuration.execution_mode = "alpaca_paper"
            client.app.state.paper_worker = worker  # type: ignore[attr-defined]

            response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "down"


@pytest.mark.parametrize("reason", ["startup_reconciliation_pending", "some_real_error"])
def test_only_the_in_progress_sentinel_is_excused_from_unhealthy(reason: str) -> None:
    worker = _worker()
    worker.degraded = True
    worker.degraded_reason = reason
    worker.has_reconciled = True

    assert worker.health_ready() is (reason == IN_PROGRESS)
