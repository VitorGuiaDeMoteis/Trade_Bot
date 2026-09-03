import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from packages.domain.market import SimulationSpec
from services.api.config import Settings, get_settings
from services.api.database import create_database_engine
from services.api.main import create_app
from services.api.market_store import MarketStore
from services.api.models import candles, system_events
from services.api.simulator_runtime import SimulatorRuntime
from services.market_simulator.generator import CandleGenerator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL de teste requerido"),
]


@pytest.fixture
def market(monkeypatch):
    for key, value in {
        "APP_ENV": "test",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5433",
        "POSTGRES_DB": "trading_bot_test",
        "POSTGRES_USER": "test_only",
        "POSTGRES_PASSWORD": "test_only",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr("test_only"),
        simulator_enabled=False,
        simulator_interval_seconds=0.1,
    )
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE system_events, candles"))
    generator = CandleGenerator(SimulationSpec())
    store = MarketStore(engine, generator.spec.stream_id)
    yield settings, engine, generator, store
    engine.dispose()
    get_settings.cache_clear()


def test_atomic_persistence_before_visibility_and_publication(market):
    _, engine, generator, store = market
    candle = generator.next_closed(1)
    with engine.begin() as connection:
        store._persist(connection, candle)
        # Outra conexão (a usada pelo WebSocket) não vê a transação aberta.
        assert store.events_after(0) == []
        assert store.history(10).candles == []
    events = store.events_after(0)
    assert len(events) == 1
    assert events[0].payload.candle_id == store.history(10).candles[0].candle_id
    assert events[0].correlation_id


def test_event_failure_rolls_back_candle(market):
    _, engine, generator, store = market
    with pytest.raises(RuntimeError):
        with engine.begin() as connection:
            store._persist(connection, generator.next_closed(1))
            raise RuntimeError("simular falha antes do commit")
    assert store.history(10).candles == []
    assert store.events_after(0) == []


def test_idempotency_restart_and_concurrent_writers(market):
    _, engine, generator, store = market
    candle = generator.next_closed(1)
    with ThreadPoolExecutor(max_workers=3) as pool:
        events = list(pool.map(lambda _: store.append(candle), range(3)))
    assert len({e.event_id for e in events}) == 1
    restarted = MarketStore(engine, store.stream_id)
    second = restarted.advance(CandleGenerator(generator.spec))
    assert second.sequence == 2
    assert second.payload.close == generator.next_closed(2, candle.close).close
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(candles)) == 2
        assert connection.scalar(select(func.count()).select_from(system_events)) == 2


def test_database_constraints_and_content_collision(market):
    _, engine, generator, store = market
    candle = generator.next_closed(1)
    store.append(candle)
    with pytest.raises(ValueError):
        store.append(replace(candle, volume=candle.volume + 1))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(candles.update().values(volume=-1))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(candles.update().values(high=1))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            row = dict(connection.execute(select(candles)).mappings().one())
            row.update(candle_id=uuid4(), sequence=2)
            connection.execute(candles.insert().values(**row))  # mesmo timestamp


def test_rest_limits_pagination_watermark_and_stream_reset(market):
    settings, _, generator, store = market
    for _ in range(8):
        store.advance(generator)
    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/v1/market/candles?limit=3")
        assert initial.status_code == 200
        body = initial.json()
        assert [c["sequence"] for c in body["candles"]] == [6, 7, 8]
        assert body["cursor"] == body["high_watermark"] == 8
        assert body["schema_version"] == "1.0"
        assert isinstance(body["candles"][0]["open"], str)
        page = client.get("/api/v1/market/candles?after=2&limit=3").json()
        assert [c["sequence"] for c in page["candles"]] == [3, 4, 5]
        assert page["has_more"]
        store.advance(generator)
        final = client.get("/api/v1/market/candles?after=5&through=8&limit=3").json()
        assert [c["sequence"] for c in final["candles"]] == [6, 7, 8]
        assert not final["has_more"]
        for query in ["limit=0", "limit=501", "after=-1"]:
            assert client.get(f"/api/v1/market/candles?{query}").status_code == 422
        assert client.get("/api/v1/market/candles?after=999").status_code == 409
        assert client.get(f"/api/v1/market/candles?stream_id={uuid4()}").status_code == 409


def test_snapshot_to_websocket_race_replay_and_status(market):
    settings, _, generator, store = market
    store.advance(generator)
    with TestClient(create_app(settings)) as client:
        snapshot = client.get("/api/v1/market/candles").json()
        # Persistência ocorre entre a resposta REST e a abertura do WebSocket.
        added = store.advance(generator)
        url = f"/api/v1/market/events?after={snapshot['cursor']}&stream_id={store.stream_id}"
        with client.websocket_connect(url) as socket:
            event = socket.receive_json()
            assert event["event_id"] == str(added.event_id)
            assert event["sequence"] == 2
            assert event["event_type"] == "market.candle.closed"
            status = socket.receive_json()
            assert status["type"] == "stream.status"
            assert status["simulator"]["state"] == "stopped"
            third = store.advance(generator)
            assert socket.receive_json()["event_id"] == str(third.event_id)
        with client.websocket_connect(
            f"/api/v1/market/events?after=2&stream_id={store.stream_id}"
        ) as ws:
            assert ws.receive_json()["sequence"] == 3


def test_empty_snapshot_and_simulator_stopped_health(market):
    settings, _, _, _ = market
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/v1/market/candles").json()
        assert body["candles"] == []
        assert body["cursor"] == 0
        health = client.get("/health")
        assert health.status_code == 503
        assert health.json()["simulator"]["state"] == "stopped"


def test_runtime_runs_stops_and_recovers_from_real_database_error(market):
    settings, engine, generator, store = market

    async def scenario():
        runtime = SimulatorRuntime(
            settings.model_copy(update={"simulator_enabled": True}), store, generator
        )
        runtime.start()
        try:
            for _ in range(100):
                if runtime.status().state == "running":
                    break
                await asyncio.sleep(0.02)
            assert runtime.status().state == "running"
            assert store.history(10).cursor > 0
            runtime.last_progress = monotonic() - 100
            assert runtime.status().state == "stalled"
        finally:
            await runtime.stop()
        assert runtime.status().state == "stopped"

        # Erro PostgreSQL real: schema temporariamente indisponível neste banco isolado.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE candles RENAME TO candles_temporarily_unavailable")
            )
        runtime.start()
        try:
            for _ in range(100):
                if runtime.status().state == "degraded":
                    break
                await asyncio.sleep(0.02)
            assert runtime.status().state == "degraded"
        finally:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE candles_temporarily_unavailable RENAME TO candles")
                )
        try:
            for _ in range(100):
                if runtime.status().state == "running":
                    break
                await asyncio.sleep(0.02)
            assert runtime.status().state == "running"
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_real_connection_failure_rest_health_and_runtime(market):
    settings, _, _, _ = market
    unavailable = settings.model_copy(update={"postgres_port": 1, "simulator_enabled": True})
    with TestClient(create_app(unavailable)) as client:
        response = client.get("/api/v1/market/candles")
        assert response.status_code == 503
        assert response.json() == {"detail": "database_unavailable"}
        deadline = monotonic() + 6
        while client.app.state.simulator.state != "degraded" and monotonic() < deadline:
            sleep(0.05)
        health = client.get("/health")
        assert health.status_code == 503
        assert health.json()["database"] == "down"
        assert health.json()["simulator"]["state"] == "degraded"
