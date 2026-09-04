import json
import os
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import event, select
from test_market_integration import market as market
from test_paper_database import Market, fingerprint, seed, state

from packages.domain.backtest import manifest
from services.api.models import candles, portfolio_snapshots, risk_decisions, signals
from services.backtesting.artifacts import load_manifest, write_artifact
from services.backtesting.engine import run
from services.backtesting.source import freeze

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


def test_every_financial_frame_matches_paper_on_postgres(market: Market) -> None:
    paper = seed(market, symbols=("SPY", "AAPL", "TSLA"))
    data = freeze(paper.engine, "alpaca", ("SPY", "AAPL", "TSLA"))
    backtest = run(data, paper.config)
    paper.replay()
    current = state(paper)
    with paper.engine.connect() as c:
        frames = (
            c.execute(select(portfolio_snapshots).order_by(portfolio_snapshots.c.step))
            .mappings()
            .all()
        )
    assert len(frames) == len(backtest["equity_curve"])
    for stored, replayed in zip(frames, backtest["equity_curve"], strict=True):
        for field in (
            "cash",
            "market_value",
            "equity",
            "realized_pnl",
            "unrealized_pnl",
            "total_pnl",
            "fees",
        ):
            assert stored[field] == D(replayed[field]), (stored["step"], field)
    assert current["fills_count"] == backtest["metrics"]["fills"]
    assert current["orders_count"] == backtest["metrics"]["orders"]
    paper.set_paused(True)
    before = fingerprint(paper.engine)
    assert backtest == run(data, paper.config)
    assert fingerprint(paper.engine) == before  # isolated research does not resume/write paper


def test_frozen_source_survives_db_change_and_offline_process_restart(
    market: Market, tmp_path: Path
) -> None:
    paper = seed(market)
    with paper.engine.connect() as c:
        before = [c.execute(select(t)).all() for t in (candles, signals, risk_decisions)]
    data = freeze(paper.engine, "alpaca", ("SPY",))
    path = tmp_path / "input.json"
    write_artifact(path, manifest(data, paper.config))
    expected = run(data, paper.config)
    with paper.engine.begin() as c:
        assert before == [c.execute(select(t)).all() for t in (candles, signals, risk_decisions)]
        c.execute(candles.update().values(volume=candles.c.volume + 1))
    assert freeze(paper.engine, "alpaca", ("SPY",)).hash != data.hash
    assert run(*load_manifest(path)) == expected
    env = {**os.environ, "POSTGRES_HOST": "unreachable.invalid", "PYTHONUTF8": "1"}
    env.pop("POSTGRES_PASSWORD", None)
    for index in (1, 2):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.backtest",
                "run",
                str(path),
                "--output",
                str(tmp_path / f"report{index}.json"),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert process.returncode == 0, process.stderr
    assert (tmp_path / "report1.json").read_bytes() == (tmp_path / "report2.json").read_bytes()
    assert json.loads((tmp_path / "report1.json").read_text()) == expected


def test_snapshot_readonly_and_missing_series_fail_closed(market: Market) -> None:
    paper = seed(market)
    observed = []

    def inspect(connection, cursor, statement, parameters, context, many):  # type: ignore[no-untyped-def]
        if statement.startswith("SELECT candles."):
            observed.append(
                (
                    connection.get_isolation_level(),
                    connection.exec_driver_sql("SHOW transaction_read_only").scalar(),
                )
            )

    event.listen(paper.engine, "before_cursor_execute", inspect)
    try:
        freeze(paper.engine, "alpaca", ("SPY",))
        with pytest.raises(ValueError, match="missing"):
            freeze(paper.engine, "alpaca", ("SPY", "ABSENT"))
    finally:
        event.remove(paper.engine, "before_cursor_execute", inspect)
    assert observed == [("REPEATABLE READ", "on")] * 2
