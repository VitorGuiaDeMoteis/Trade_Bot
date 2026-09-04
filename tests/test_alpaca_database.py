"""Real PostgreSQL tests for M1.5, always on disposable localhost:5433."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_market_integration import market as market

from packages.contracts.market import MarketDataStatus
from packages.contracts.provider import MarketDataProvider
from packages.domain.market_bar import MarketBar, series_id
from services.api.main import create_app
from services.api.market_store import MarketStore
from services.api.models import (
    candles,
    legacy_market_archive,
    risk_decisions,
    signals,
    system_events,
)
from services.api.simulator_runtime import SimulatorRuntime
from services.market_data.errors import ContentConflict, PartialCandle
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]


def bar(symbol="SPY", hour=14):  # type: ignore
    opened = datetime(2026, 9, 3, hour, tzinfo=UTC)
    return MarketBar(
        "alpaca",
        symbol,
        "1h",
        opened,
        opened + timedelta(hours=1),
        Decimal("100.1234567890"),
        Decimal("102"),
        Decimal("99"),
        Decimal("101"),
        123,
        True,
    )


def store_for(engine, symbol="SPY", strategy=None):  # type: ignore
    return MarketStore(
        engine,
        series_id("alpaca", symbol, "1h"),
        strategy=strategy or BaseStrategy(),
        risk=RiskEngine(),
    )


def counts(engine):  # type: ignore
    with engine.connect() as connection:
        return [
            connection.scalar(select(func.count()).select_from(table))
            for table in (candles, system_events, signals, risk_decisions)
        ]


def test_history_repeat_restart_reconnect_and_concurrent_duplicates(market):  # type: ignore
    _, engine, _, _ = market
    store = store_for(engine)  # type: ignore
    data = [bar(hour=hour) for hour in (14, 15, 16)]  # type: ignore
    for item in data:
        store.append(item)
    baseline = store.events_after(0)
    assert counts(engine) == [3] * 4  # type: ignore
    for _ in range(2):
        store = store_for(engine)  # type: ignore
        for item in data:
            store.append(item)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(store.append, [data[-1]] * 3))
    assert store.events_after(0) == baseline and counts(engine) == [3] * 4  # type: ignore
    assert [e.sequence for e in store.events_after(1)] == [2, 3]
    assert store.history(3).candles[0].open == data[0].open


def test_multi_symbol_same_time_independent_cursors_and_rest_ws(market):  # type: ignore
    settings, engine, _, _ = market
    stores = {symbol: store_for(engine, symbol) for symbol in ("SPY", "AAPL")}  # type: ignore
    for symbol, store in stores.items():
        store.append(bar(symbol))  # type: ignore
    stores["SPY"].append(bar("SPY", 15))  # type: ignore
    assert counts(engine) == [3] * 4  # type: ignore
    with TestClient(create_app(settings)) as client:
        client.app.state.markets = stores  # type: ignore
        client.app.state.configuration = settings.model_copy(  # type: ignore
            update={"market_data_provider": "alpaca", "market_symbols": "SPY,AAPL"}
        )
        for symbol in stores:
            response = client.get(f"/api/v1/market/candles?symbol={symbol}&timeframe=1h")
            assert response.status_code == 200
            page = response.json()
            assert {c["symbol"] for c in page["candles"]} == {symbol}
            assert page["symbol"] == symbol
            assert [c["sequence"] for c in page["candles"]] == ([1, 2] if symbol == "SPY" else [1])
            with client.websocket_connect(
                f"/api/v1/market/events?symbol={symbol}&stream_id={page['stream_id']}&after=0"
            ) as ws:
                event = ws.receive_json()
                assert event["sequence"] == 1 and event["payload"]["symbol"] == symbol
        assert client.get("/api/v1/market/candles?symbol=NOPE").status_code == 422
        assert client.get("/api/v1/market/candles?symbol=SPY&timeframe=1m").status_code == 422
        assert (
            client.get(
                f"/api/v1/market/candles?symbol=AAPL&stream_id={stores['SPY'].stream_id}"
            ).status_code
            == 409
        )


def test_conflict_partial_and_future_never_reprocess(market):  # type: ignore
    _, engine, _, _ = market
    store = store_for(engine)  # type: ignore
    item = bar()  # type: ignore
    event = store.append(item)
    for changed in [replace(item, volume=124), replace(item, close=Decimal("100"))]:
        with pytest.raises(ContentConflict):
            store.append(changed)
    with pytest.raises(PartialCandle):
        store.append(replace(bar(hour=15), is_closed=False))  # type: ignore
    opened = datetime.now(UTC) + timedelta(hours=1)
    future = replace(bar(hour=15), open_time=opened, close_time=opened + timedelta(hours=1))  # type: ignore
    # Dataclass construction needs exact duration.
    with pytest.raises(PartialCandle):
        store.append(replace(future, close_time=future.open_time + timedelta(hours=1)))
    assert counts(engine) == [1] * 4 and store.events_after(0) == [event]  # type: ignore


def test_strategy_failure_rolls_back_all_writes_and_no_cursor_gap(market):  # type: ignore
    _, engine, _, _ = market

    class FailingStrategy(BaseStrategy):
        def process_candle(self, candle, current_time):  # type: ignore
            raise RuntimeError("strategy failure")

    with pytest.raises(RuntimeError):
        store_for(engine, strategy=FailingStrategy()).append(bar())  # type: ignore
    assert counts(engine) == [0] * 4  # type: ignore
    assert store_for(engine).append(bar()).sequence == 1  # type: ignore
    assert counts(engine) == [1] * 4  # type: ignore


def test_database_unique_signal_risk_and_closed_constraints(market):  # type: ignore
    _, engine, _, _ = market
    store_for(engine).append(bar())  # type: ignore
    for table, identity in ((signals, "signal_id"), (risk_decisions, "decision_id")):
        with engine.connect() as connection:
            duplicate = dict(connection.execute(select(table)).mappings().one())
        from uuid import uuid4

        duplicate[identity] = uuid4()
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(table.insert().values(**duplicate))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(candles.update().values(is_closed=False))
    assert counts(engine) == [1] * 4  # type: ignore


def test_runtime_conflict_is_visible_and_stops_processing(market, caplog):  # type: ignore
    settings, engine, generator, _ = market
    store = store_for(engine)  # type: ignore
    store.append(bar())  # type: ignore

    class FakeProvider(MarketDataProvider):
        async def get_historical_candles(self, *args, **kwargs):  # type: ignore
            return [replace(bar(), volume=999)]  # type: ignore

        async def subscribe(self):  # type: ignore
            raise AssertionError("Conflict must stop before subscription")
            yield

        def get_status(self):  # type: ignore
            return MarketDataStatus(provider="alpaca", state="connected", symbols=["SPY"])

    runtime = SimulatorRuntime(
        settings.model_copy(update={"market_data_provider": "alpaca", "market_symbols": "SPY"}),
        store,
        FakeProvider(),
        {"SPY": store},
    )
    asyncio.run(runtime._run())
    assert runtime.status().state == "degraded"
    assert runtime.error == "market_identity_content_conflict"
    assert '"event": "market.ingestion.failed"' in caplog.text
    assert counts(engine) == [1] * 4  # type: ignore


def test_migration_quarantine_preserves_complete_graph_and_downgrade(market):  # type: ignore
    _, engine, generator, _ = market
    config = Config("alembic.ini")
    command.downgrade(config, "d4ae1863048a")
    old = replace(generator.next_closed(1), provider="alpaca", symbol="SPY")
    values = asdict(old)
    values.pop("is_closed")
    with engine.begin() as connection:
        # Insert through SQL at old revision (new metadata contains is_closed).
        columns = ", ".join('"' + name + '"' for name in values)
        placeholders = ", ".join(":" + name for name in values)
        connection.execute(text(f"INSERT INTO candles ({columns}) VALUES ({placeholders})"), values)
        from uuid import uuid4

        event_id = uuid4()
        signal = BaseStrategy().process_candle(old, datetime.now(UTC))
        decision = RiskEngine().evaluate(signal, datetime.now(UTC))
        connection.execute(
            system_events.insert().values(
                event_id=event_id,
                candle_id=old.candle_id,
                stream_id=old.stream_id,
                sequence=old.sequence,
                event_type="market.candle.closed",
                schema_version="1.0",
                occurred_at=datetime.now(UTC),
                correlation_id=uuid4(),
            )
        )
        connection.execute(signals.insert().values(**asdict(signal)))
        connection.execute(risk_decisions.insert().values(**asdict(decision)))
    command.upgrade(config, "head")
    assert counts(engine) == [0] * 4  # type: ignore
    with engine.connect() as connection:
        archive = connection.execute(select(legacy_market_archive)).mappings().all()
        assert len(archive) == 4
        archived = next(row for row in archive if row["kind"] == "candles")
        assert archived["payload"]["candle_id"] == str(old.candle_id)
        assert archived["payload"]["provider"] == "alpaca"
    command.downgrade(config, "d4ae1863048a")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM candles")) == 1
    command.upgrade(config, "head")
    command.check(config)


def test_backend_lifespan_restart_backfill_and_websocket_duplicate(market):  # type: ignore
    from time import monotonic, sleep
    from unittest.mock import patch

    from pydantic import SecretStr

    settings, engine, _, _ = market
    data = [bar(hour=14), bar(hour=15)]  # type: ignore

    class FakeProvider(MarketDataProvider):
        async def get_historical_candles(self, *args, **kwargs):  # type: ignore
            return data

        async def subscribe(self):  # type: ignore
            for item in data:
                yield item
            await asyncio.sleep(3600)

        def get_status(self):  # type: ignore
            return MarketDataStatus(provider="alpaca", state="connected", symbols=["SPY"])

    configured = settings.model_copy(
        update={
            "market_data_provider": "alpaca",
            "market_symbols": "SPY",
            "alpaca_api_key_id": SecretStr("fake-key"),
            "alpaca_api_secret_key": SecretStr("fake-secret"),
        }
    )
    previous = None
    for _ in range(2):
        with patch(
            "services.api.main.AlpacaMarketDataProvider", side_effect=lambda **kw: FakeProvider()
        ):
            with TestClient(create_app(configured)) as client:
                deadline = monotonic() + 3
                while counts(engine) != [2] * 4 and monotonic() < deadline:  # type: ignore
                    sleep(0.01)
                assert counts(engine) == [2] * 4  # type: ignore
                page = client.get("/api/v1/market/candles?symbol=SPY").json()
                assert page["cursor"] == 2
                with client.websocket_connect(
                    f"/api/v1/market/events?symbol=SPY&stream_id={page['stream_id']}&after=1"
                ) as ws:
                    event = ws.receive_json()
                    assert event["sequence"] == 2
                    if previous is not None:
                        assert event == previous
                    previous = event
    assert counts(engine) == [2] * 4  # type: ignore
