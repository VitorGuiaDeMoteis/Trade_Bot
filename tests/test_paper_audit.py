"""Regressions for the final M3 financial/persistence audit; dedicated test DB only."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_market_integration import market as market
from test_paper_database import Market, fingerprint, seed, state

from services.api.main import create_app
from services.api.models import (
    candles,
    paper_marks,
    paper_orders,
    paper_runs,
    portfolio_snapshots,
    signals,
    system_controls,
)
from services.api.paper_store import PaperPaused, PaperStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "target",
    [
        "dataset",
        "completed_cash",
        "checkpoint",
        "order_signal",
        "missing_mark",
        "old_snapshot",
        "missing_control",
    ],
)
def test_corrupt_replay_is_rejected_without_writes(market: Market, target: str) -> None:
    store = seed(market)
    store.replay(max_steps=None if target == "completed_cash" else 4)
    with store.engine.begin() as c:
        if target == "dataset":
            dataset = deepcopy(c.scalar(select(paper_runs.c.dataset)))
            dataset[5]["candle"]["volume"] += 1
            c.execute(paper_runs.update().values(dataset=dataset))
        elif target == "completed_cash":
            c.execute(paper_runs.update().values(cash=paper_runs.c.cash + 1))
        elif target == "checkpoint":
            c.execute(paper_runs.update().values(step=999))
        elif target == "order_signal":
            first = c.execute(select(paper_orders)).mappings().first()
            other = c.scalar(
                select(signals.c.signal_id).where(signals.c.signal_id != first["signal_id"])
            )
            c.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == first["order_id"])
                .values(signal_id=other)
            )
        elif target == "missing_mark":
            c.execute(paper_marks.delete())  # flat portfolio: arithmetic alone cannot detect this
        elif target == "missing_control":
            c.execute(system_controls.delete())
        else:
            c.execute(
                portfolio_snapshots.update().where(portfolio_snapshots.c.step == 1).values(fees=1)
            )
    before = fingerprint(store.engine)
    with pytest.raises(ValueError, match="paper_"):
        store.replay()
    assert fingerprint(store.engine) == before
    with TestClient(create_app(market[0])) as client:
        response = client.get("/api/v1/paper/portfolio")
        assert response.status_code == 503
        assert response.json()["detail"] == "paper_reconciliation_failed"
        assert client.get("/api/v1/decisions").status_code == 503


def test_reset_decisions_only_link_active_run(market: Market) -> None:
    store = seed(market)
    store.replay()
    new = store.initialize(reset=True)
    store.replay()
    with TestClient(create_app(market[0])) as client:
        client.app.state.configuration = store.settings  # type: ignore[attr-defined]
        from packages.domain.market_bar import series_id
        from services.api.market_store import MarketStore

        client.app.state.markets = {
            "SPY": MarketStore(store.engine, series_id("alpaca", "SPY", "1h"))
        }  # type: ignore[attr-defined]
        items = client.get("/api/v1/decisions?symbol=SPY").json()["items"]
        assert len(items) == 7
        assert len({item["signal"]["signal_id"] for item in items}) == 7
        assert all(item["paper"]["run_id"] == str(new) for item in items)
        assert "test-paper-pause-only" not in json.dumps(items)


@pytest.mark.parametrize("table", ["positions", "portfolio_snapshots"])
def test_late_write_failure_rolls_back_every_paper_table(market: Market, table: str) -> None:
    store = seed(market)
    store.replay(max_steps=1)
    before = fingerprint(store.engine)

    def fail_after_write(*args: Any) -> None:
        if args[2].startswith("INSERT INTO " + table + " "):
            raise RuntimeError("late financial write failed")

    event.listen(store.engine, "after_cursor_execute", fail_after_write)
    try:
        with pytest.raises(RuntimeError, match="late financial write"):
            store.replay(max_steps=2)
    finally:
        event.remove(store.engine, "after_cursor_execute", fail_after_write)
    assert fingerprint(store.engine) == before
    store.replay(max_steps=2)
    assert state(store)["orders_count"] == state(store)["fills_count"] == 1


def test_pause_waits_for_atomic_batch_then_blocks_next_batch(market: Market) -> None:
    store = seed(market)
    store.replay(max_steps=1)
    before = state(store)
    fill_written, release, pause_started = Event(), Event(), Event()

    def hold_transaction() -> None:
        fill_written.set()
        assert release.wait(10), "test transaction timed out"

    def pause() -> None:
        pause_started.set()
        store.set_paused(True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(store.replay, max_steps=2, after_fill=hold_transaction)
        try:
            assert fill_written.wait(10)
            pausing = pool.submit(pause)
            assert pause_started.wait(10)
            assert not pausing.done()
            # No uncommitted fill/cash/position is exposed to concurrent readers.
            assert state(store) == before
        finally:
            release.set()
        running.result(timeout=10)
        pausing.result(timeout=10)
    after = state(store)
    assert after["paused"] and after["orders_count"] == after["fills_count"] == 1
    assert len(after["positions"]) == 1
    before = fingerprint(store.engine)
    with pytest.raises(PaperPaused):
        store.replay()
    assert fingerprint(store.engine) == before


def test_insufficient_capital_persists_rejections_without_financial_mutation(
    market: Market,
) -> None:
    seeded = seed(market)
    store = PaperStore(
        seeded.engine, seeded.settings.model_copy(update={"paper_initial_cash": Decimal("50")})
    )
    store.replay()
    result = state(store)
    assert result["orders_count"] == 3 and result["fills_count"] == 0
    assert result["positions"] == []
    assert Decimal(result["cash"]) == Decimal(result["equity"]) == Decimal("50")
    assert Decimal(result["fees"]) == Decimal(result["total_pnl"]) == 0
    assert all(o["status"] == "REJECTED" and o["quantity"] == 0 for o in result["orders"])
    assert all(o["reason"] == "position_size_below_one_share" for o in result["orders"])


def test_staggered_cross_asset_candles_cannot_expose_future_close(market: Market) -> None:
    store = seed(market, symbols=("AAPL", "SPY"))
    with store.engine.begin() as c:
        c.execute(
            candles.update()
            .where(candles.c.symbol == "AAPL")
            .values(
                open_time=candles.c.open_time + timedelta(minutes=30),
                close_time=candles.c.close_time + timedelta(minutes=30),
            )
        )
    with pytest.raises(ValueError, match="paper_"):
        store.replay()
    with store.engine.connect() as c:
        assert c.execute(select(paper_orders)).all() == []
