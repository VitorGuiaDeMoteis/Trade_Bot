import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from test_market_integration import market as market

from packages.domain.market_bar import MarketBar, series_id
from services.api.config import Settings
from services.api.main import create_app
from services.api.market_store import MarketStore
from services.api.models import (
    PAPER_TABLES,
    candles,
    paper_fills,
    paper_orders,
    paper_outcomes,
    paper_runs,
    portfolio_snapshots,
    risk_decisions,
    signals,
)
from services.api.paper_queries import portfolio
from services.api.paper_store import PaperPaused, PaperStore
from services.market_simulator.generator import CandleGenerator
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]
Market = tuple[Settings, Engine, CandleGenerator, MarketStore]


def seed(
    market: Market,
    symbols: tuple[str, ...] = ("SPY",),
    values: list[tuple[str, str]] | None = None,
    gap: bool = False,
) -> PaperStore:
    settings, engine, _, _ = market
    prices = values or [
        ("100", "101"),
        ("110", "111"),
        ("120", "119"),
        ("130", "130"),
        ("140", "139"),
        ("150", "151"),
        ("160", "161"),
    ]
    for symbol in symbols:
        source = MarketStore(
            engine, series_id("alpaca", symbol, "1h"), strategy=BaseStrategy(), risk=RiskEngine()
        )
        for index, (opening, closing) in enumerate(prices):
            opened = datetime(2026, 1, 2, 10, tzinfo=UTC) + timedelta(
                hours=index * (24 if gap else 1)
            )
            source.append(
                MarketBar(
                    "alpaca",
                    symbol,
                    "1h",
                    opened,
                    opened + timedelta(hours=1),
                    D(opening),
                    max(D(opening), D(closing)),
                    min(D(opening), D(closing)),
                    D(closing),
                    100,
                    True,
                )
            )
    return PaperStore(
        engine,
        settings.model_copy(
            update={
                "market_data_provider": "alpaca",
                "market_symbols": ",".join(symbols),
            }
        ),
    )


def state(store: PaperStore) -> dict[str, Any]:
    with store.engine.connect() as c:
        return portfolio(c, store).model_dump(mode="json")


def fingerprint(engine: Engine) -> list[str]:
    with engine.connect() as c:
        return sorted(
            json.dumps(dict(r), default=str, sort_keys=True)
            for t in PAPER_TABLES
            for r in c.execute(select(t)).mappings()
        )


def test_replay_restart_idempotency_and_positions_survive(market: Market) -> None:
    store = seed(market)
    store.replay(max_steps=2)
    assert state(store)["positions"][0]["quantity"] == 9
    new = PaperStore(store.engine, store.settings)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: new.replay(), range(2)))
    final = state(new)
    assert final["status"] == "COMPLETED" and final["reconciled"]
    assert final["orders_count"] == final["fills_count"] == 3
    assert len(final["positions"]) == 1 and final["positions"][0]["quantity"] > 0
    assert D(final["equity"]) == D(final["cash"]) + D(final["market_value"])
    assert D(final["total_pnl"]) == D(final["realized_pnl"]) + D(final["unrealized_pnl"]) - D(
        final["fees"]
    )
    before = fingerprint(store.engine)
    new.replay()
    assert fingerprint(store.engine) == before
    # Two actual FastAPI lifespans, offline provider; reading paper survives restarts.
    for _ in range(2):
        with TestClient(create_app(market[0])) as client:
            client.app.state.configuration = store.settings  # type: ignore[attr-defined]
            assert client.get("/api/v1/paper/portfolio").json() == final
    assert fingerprint(store.engine) == before


def test_unique_risk_order_and_unique_order_fill(market: Market) -> None:
    store = seed(market)
    store.replay()
    for table, identity in ((paper_orders, "order_id"), (paper_fills, "fill_id")):
        with store.engine.connect() as c:
            row = dict(c.execute(select(table)).mappings().first())  # type: ignore
        row[identity] = uuid4()
        if table is paper_orders:
            row["idempotency_key"] = uuid4()
        with pytest.raises(IntegrityError), store.engine.begin() as c:
            c.execute(table.insert().values(**row))


def test_failure_after_fill_rolls_back_whole_group(market: Market) -> None:
    store = seed(market)

    def fail() -> None:
        raise RuntimeError("injected after fill")

    with pytest.raises(RuntimeError, match="injected"):
        store.replay(after_fill=fail)
    failed = state(store)
    assert failed["cash"] == "10000.0000000000" and failed["step"] == 1
    assert failed["orders_count"] == failed["fills_count"] == 0 and failed["positions"] == []
    store.replay()
    assert state(store)["orders_count"] == 3


def test_local_stop_blocks_replay_preserves_positions(market: Market) -> None:
    store = seed(market)
    store.replay(max_steps=2)
    before = state(store)
    with TestClient(
        create_app(market[0]), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)
    ) as client:
        client.app.state.configuration = store.settings  # type: ignore[attr-defined]
        assert client.post("/api/v1/paper/pause").status_code == 403
        headers = {"X-Paper-Control": "stop"}
        assert (
            client.post(
                "/api/v1/paper/pause", headers={**headers, "Origin": "http://example.com"}
            ).status_code
            == 403
        )
        assert client.post("/api/v1/paper/pause", headers=headers).json() == {"paused": True}
        paused_rows = fingerprint(store.engine)
        assert client.post("/api/v1/paper/pause", headers=headers).status_code == 200
        assert fingerprint(store.engine) == paused_rows
        with pytest.raises(PaperPaused):
            PaperStore(store.engine, store.settings).replay()
        after = client.get("/api/v1/paper/portfolio").json()
        assert after["paused"] and after["positions"] == before["positions"]
        assert after["cash"] == before["cash"] and after["orders_count"] == before["orders_count"]
        for route in ("/buy", "/sell", "/order", "/reset", "/resume"):
            assert client.post("/api/v1/paper" + route).status_code == 404
    store.set_paused(False)
    store.replay()
    assert state(store)["orders_count"] == 3


def test_risk_rejected_and_hold_never_call_executor(market: Market) -> None:
    store = seed(market, values=[("100", "101"), ("100", "100"), ("100", "101")])
    with store.engine.begin() as c:
        first = c.scalar(
            select(signals.c.signal_id).join(candles).order_by(candles.c.open_time).limit(1)
        )
        c.execute(
            risk_decisions.update()
            .where(risk_decisions.c.signal_id == first)
            .values(decision="REJECTED", reason="Sistema pausado.")
        )
    with patch(
        "services.api.paper_store.PaperExecutor.execute",
        side_effect=AssertionError("must not execute"),
    ):
        store.replay()
    assert state(store)["orders_count"] == 0
    with store.engine.connect() as c:
        assert set(c.scalars(select(paper_outcomes.c.reason))) == {"hold", "risk_rejected"}


def test_safe_reset_preserves_source_and_old_run_and_reproduces_money(market: Market) -> None:
    store = seed(market)
    old = store.replay()
    before = state(store)
    with store.engine.connect() as c:
        source = [c.execute(select(t)).all() for t in (candles, signals, risk_decisions)]
    new = store.initialize(reset=True)
    assert new != old and state(store)["orders_count"] == 0
    assert D(state(store)["cash"]) == D("10000")
    store.replay()
    after = state(store)
    for field in (
        "cash",
        "equity",
        "fees",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "positions",
        "orders_count",
        "fills_count",
    ):
        assert before[field] == after[field]
    with store.engine.connect() as c:
        assert source == [c.execute(select(t)).all() for t in (candles, signals, risk_decisions)]
        assert len(c.execute(select(paper_orders).where(paper_orders.c.run_id == old)).all()) == 3


def test_no_cross_asset_lookahead_and_frozen_dataset(market: Market) -> None:
    store = seed(market, symbols=("AAPL", "SPY"), values=[("100", "101"), ("100", "1000000")])
    run = store.initialize()
    store.replay()
    current = state(store)
    assert current["dataset_count"] == 4
    assert [p["quantity"] for p in current["positions"]] == [9, 9]
    assert {f["reference_price"] for f in current["fills"]} == {"100.0000000000"}
    with store.engine.begin() as c:
        c.execute(candles.update().where(candles.c.symbol == "AAPL").values(volume=999))
    assert store.replay() == run and state(store) == current  # input is the frozen original dataset


def test_expired_virtual_signal_no_order(market: Market) -> None:
    store = seed(market, values=[("100", "101"), ("100", "101")], gap=True)
    store.replay()
    assert state(store)["orders_count"] == 0
    with store.engine.connect() as c:
        assert c.scalar(select(paper_outcomes.c.reason)) == "expired_replay_signal"


@pytest.mark.parametrize("target", ["cash", "fee", "snapshot"])
def test_reconciliation_detects_corruption_and_api_fails_closed(
    market: Market, target: str
) -> None:
    store = seed(market)
    store.replay(max_steps=2)
    with store.engine.begin() as c:
        if target == "cash":
            c.execute(paper_runs.update().values(cash=paper_runs.c.cash + 1))
        elif target == "fee":
            c.execute(paper_fills.update().values(fee=paper_fills.c.fee + 1))
        else:
            c.execute(portfolio_snapshots.update().values(fees=portfolio_snapshots.c.fees + 1))
    with pytest.raises(ValueError):
        store.replay()
    with TestClient(create_app(market[0])) as client:
        response = client.get("/api/v1/paper/portfolio")
        assert (
            response.status_code == 503
            and response.json()["detail"] == "paper_reconciliation_failed"
        )


def test_paper_api_links_positions_orders_fills_and_empty(market: Market) -> None:
    with TestClient(create_app(market[0])) as client:
        empty = client.get("/api/v1/paper/portfolio").json()
        assert empty["status"] == "EMPTY" and empty["positions"] == []
        assert empty["currency"] == "USD" and empty["mode"] == "REPLAY"
        assert client.post("/api/v1/paper/pause").status_code == 403
        store = seed(market)
        store.replay()
        client.app.state.configuration = store.settings  # type: ignore[attr-defined]
        client.app.state.markets = {  # type: ignore
            "SPY": MarketStore(store.engine, series_id("alpaca", "SPY", "1h"))
        }
        orders = client.get("/api/v1/paper/orders?limit=2").json()["items"]
        fills = client.get("/api/v1/paper/fills?limit=2").json()["items"]
        assert len(orders) == len(fills) == 2
        assert {o["order_id"] for o in orders} == {f["order_id"] for f in fills}
        assert len(client.get("/api/v1/paper/positions").json()["items"]) == 1
        assert client.get("/api/v1/paper/orders?limit=201").status_code == 422
        decisions = client.get("/api/v1/decisions?symbol=SPY").json()["items"]
        assert decisions[0]["paper"]["status"] == "WAITING"
        executed = [d for d in decisions if d["paper"]["status"] == "FILLED"]
        assert len(executed) == 3
        assert all(d["paper"]["order"]["signal_id"] == d["signal"]["signal_id"] for d in executed)
        assert all(
            d["paper"]["fill"]["order_id"] == d["paper"]["order"]["order_id"] for d in executed
        )
        assert all(UUID(d["paper"]["run_id"]) for d in decisions)
