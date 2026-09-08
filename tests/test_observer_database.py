import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from test_market_integration import market as market
from test_observer import BadProvider, raw_snapshot
from test_paper_database import fingerprint as paper_fingerprint
from test_paper_database import seed

from services.api.models import observer_analysis_runs, risk_decisions, signals
from services.api.observer_source import collect
from services.api.observer_store import analyze
from services.observer.provider import FakeProvider
from services.observer.snapshot import project

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


def fingerprint(engine):
    with engine.connect() as c:
        decisions = sorted(
            json.dumps(dict(row), default=str, sort_keys=True)
            for table in (signals, risk_decisions)
            for row in c.execute(select(table)).mappings()
        )
    return paper_fingerprint(engine) + decisions


@pytest.fixture
def audit(market):
    engine = market[1]
    with engine.begin() as c:
        c.execute(text("TRUNCATE observer_analysis_runs"))
    yield engine
    with engine.begin() as c:
        c.execute(text("TRUNCATE observer_analysis_runs"))


def test_observer_readonly_snapshot_and_config_secrets_never_cross_boundary(
    market, audit, monkeypatch
):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PLANTED_ALPACA_KEY_DO_NOT_SEND")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "PLANTED_ALPACA_SECRET_DO_NOT_SEND")
    paper = seed(market)
    paper.replay(max_steps=2)
    paper.set_paused(True)
    # Seed historical generation timestamps explicitly; the source must never
    # replace the actual persisted generation time with the candle's time.
    with audit.begin() as c:
        c.execute(
            text(
                "UPDATE signals SET generated_at=c.close_time FROM candles c "
                "WHERE signals.candle_id=c.candle_id"
            )
        )
        c.execute(
            text(
                "UPDATE risk_decisions SET decided_at=s.generated_at FROM signals s "
                "WHERE risk_decisions.signal_id=s.signal_id"
            )
        )
    before = fingerprint(audit)
    access = []

    def inspect(c, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT candles."):
            access.append(
                (c.get_isolation_level(), c.exec_driver_sql("SHOW transaction_read_only").scalar())
            )

    event.listen(audit, "before_cursor_execute", inspect)
    try:
        snapshot = collect(
            audit,
            as_of=datetime(2026, 1, 2, 17, tzinfo=UTC),
            provider="alpaca",
            session_state="connected",
            symbols=("SPY",),
        )
    finally:
        event.remove(audit, "before_cursor_execute", inspect)
    assert access == [("REPEATABLE READ", "on")]
    assert snapshot.paper.paused and snapshot.paper.positions[0].quantity == 9
    encoded = snapshot.payload().decode()
    for forbidden in (
        "PLANTED",
        "test_only",
        "postgres",
        "database_url",
        "signal_id",
        "account",
        "reason",
        "run_id",
    ):
        assert forbidden not in encoded
    assert len(snapshot.candles) == 7 and len(snapshot.signals) == len(snapshot.risk_decisions) == 1
    result = analyze(audit, uuid4(), snapshot, FakeProvider(), enabled=True)
    assert result["status"] == "OK"
    assert fingerprint(audit) == before


@pytest.mark.parametrize(
    "payload",
    [
        b"{broken",
        b"x" * 20000,
        RuntimeError("ALPACA_API_SECRET_KEY=planted"),
        FileNotFoundError("secretpath"),
        TimeoutError("private detail"),
    ],
)
def test_model_error_persists_hold_and_never_changes_paper(market, audit, payload):
    paper = seed(market)
    paper.replay(max_steps=2)
    paper.set_paused(True)
    before = fingerprint(audit)
    ident = uuid4()
    result = analyze(audit, ident, project(raw_snapshot()), BadProvider(payload), enabled=True)
    assert result["status"] == "DEGRADED" and result["fallback"] == "HOLD"
    assert result["validated_output"] is None and "planted" not in str(result)
    with audit.connect() as c:
        stored = (
            c.execute(
                select(observer_analysis_runs).where(observer_analysis_runs.c.analysis_id == ident)
            )
            .mappings()
            .one()
        )
        assert stored["input_hash"] == result["input_hash"]
        assert (
            stored["prompt_version"] == "observer-v1"
            and stored["model"] == "deterministic-observer"
        )
        assert stored["as_of_utc"] == result["as_of_utc"]
    assert fingerprint(audit) == before


def test_restart_concurrency_and_idempotency_conflict(audit):
    snapshot = project(raw_snapshot())
    ident = uuid4()

    class Count(FakeProvider):
        calls = 0

        async def generate(self, snapshot, prompt):
            self.calls += 1
            return await super().generate(snapshot, prompt)

    provider = Count()

    def run(_):
        return analyze(audit, ident, snapshot, provider, enabled=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1] and provider.calls == 1
    assert (
        analyze(audit, ident, snapshot, BadProvider(AssertionError("must not run")), enabled=True)
        == results[0]
    )
    with pytest.raises(ValueError, match="conflict"):
        analyze(audit, ident, snapshot, provider, enabled=False)
    with audit.connect() as c:
        assert c.scalar(select(func.count()).select_from(observer_analysis_runs)) == 1


def test_disabled_and_invalid_input_persist_without_financial_effect(market, audit):
    paper = seed(market)
    paper.replay(max_steps=2)
    before = fingerprint(audit)
    for snapshot in (None, project(raw_snapshot())):
        result = analyze(audit, uuid4(), snapshot, BadProvider(AssertionError("must not run")))
        assert result["status"] == "DEGRADED" and result["fallback"] == "HOLD"
    assert fingerprint(audit) == before


def test_failure_during_audit_insert_leaves_no_partial_row(audit):
    def fail(c, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO observer_analysis_runs"):
            raise RuntimeError("injected persistence failure")

    event.listen(audit, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            analyze(audit, uuid4(), project(raw_snapshot()), FakeProvider(), enabled=True)
    finally:
        event.remove(audit, "before_cursor_execute", fail)
    with audit.connect() as c:
        assert c.scalar(select(func.count()).select_from(observer_analysis_runs)) == 0


def test_audit_corruption_is_not_returned_as_cached_success(audit):
    ident = uuid4()
    snapshot = project(raw_snapshot())
    analyze(audit, ident, snapshot, FakeProvider(), enabled=True)
    with audit.begin() as c:
        c.execute(observer_analysis_runs.update().values(output_hash="0" * 64))
    with pytest.raises(ValueError, match="corrupt"):
        analyze(audit, ident, snapshot, FakeProvider(), enabled=True)


def test_snapshot_excludes_future_facts_and_keeps_latest_known_risk(market, audit):
    seed(market)
    selection = dict(
        as_of=datetime(2026, 1, 2, 17, tzinfo=UTC),
        provider="alpaca",
        session_state="connected",
        symbols=("SPY",),
    )
    historical = collect(audit, **selection)
    assert not historical.signals and not historical.risk_decisions
    with audit.begin() as c:
        c.execute(
            text(
                "UPDATE signals SET generated_at=c.close_time FROM candles c "
                "WHERE signals.candle_id=c.candle_id"
            )
        )
        c.execute(
            text(
                "UPDATE risk_decisions SET decided_at=s.generated_at FROM signals s "
                "WHERE risk_decisions.signal_id=s.signal_id AND "
                "s.generated_at < '2026-01-02 17:00:00+00'"
            )
        )
    known = collect(audit, **selection)
    assert known.signals[0].generated_at.hour == 17
    assert known.risk_decisions[0].decided_at.hour == 16
    assert known.paper is None


@pytest.mark.parametrize("timeout", [0, -1, 31, float("nan"), float("inf")])
def test_invalid_timeout_persists_hold(audit, timeout):
    result = analyze(
        audit, uuid4(), project(raw_snapshot()), FakeProvider(), enabled=True, timeout=timeout
    )
    assert result["error_code"] == "INVALID_TIMEOUT" and result["fallback"] == "HOLD"
