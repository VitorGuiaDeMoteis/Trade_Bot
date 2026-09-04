import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import OperationalError
from test_market_integration import market as market

from packages.domain.market_bar import MarketBar, series_id
from services.api.config import Settings
from services.api.main import create_app
from services.api.market_store import MarketStore
from services.api.models import risk_decisions, signals
from services.market_simulator.generator import CandleGenerator
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Dedicated PostgreSQL required"),
]
MarketFixture = tuple[Settings, Engine, CandleGenerator, MarketStore]


def test_decisions_series_order_limit_read_only_and_database_failure(market: MarketFixture) -> None:
    settings, engine, _, _ = market
    stores = {}
    for symbol in ("SPY", "AAPL", "TSLA"):
        store = MarketStore(
            engine,
            series_id("alpaca", symbol, "1h"),
            strategy=BaseStrategy(),
            risk=RiskEngine(),
        )
        stores[symbol] = store
        # Late backfill: cursor order deliberately differs from market time order.
        for hour, close in [(15, "101"), (14, "99"), (16, "100")]:
            opened = datetime(2026, 1, 2, hour, tzinfo=UTC)
            store.append(
                MarketBar(
                    "alpaca",
                    symbol,
                    "1h",
                    opened,
                    opened + timedelta(hours=1),
                    Decimal("100"),
                    Decimal("102"),
                    Decimal("98"),
                    Decimal(close),
                    123,
                    True,
                )
            )
    with engine.connect() as connection:
        before = connection.execute(select(risk_decisions)).all()
    with TestClient(create_app(settings)) as client:
        client.app.state.markets = stores  # type: ignore[attr-defined]
        client.app.state.configuration = settings.model_copy(  # type: ignore[attr-defined]
            update={"market_symbols": "SPY,AAPL,TSLA", "market_data_provider": "alpaca"}
        )
        for symbol in stores:
            result = client.get(f"/api/v1/decisions?symbol={symbol}")
            assert result.status_code == 200
            data = result.json()
            assert data["schema_version"] == "1.0" and data["execution"] == "NONE"
            assert data["correlation_id"] == result.headers["X-Correlation-ID"]
            assert result.headers["Cache-Control"] == "no-store"
            assert data["symbol"] == symbol and data["symbols"] == list(stores)
            items = data["items"]
            assert len(items) == 3
            assert {i["candle"]["symbol"] for i in items} == {symbol}
            assert [i["signal"]["signal_type"] for i in items] == ["HOLD", "BUY", "SELL"]
            assert [i["candle"]["sequence"] for i in items] == [3, 1, 2]
            for item in items:
                assert item["signal"]["candle_id"] == item["candle"]["candle_id"]
                assert item["risk"]["signal_id"] == item["signal"]["signal_id"]
                assert item["signal"]["reason"] and item["risk"]["reason"]
                assert item["signal"]["strategy_version"] == "v1-deterministic"
                assert isinstance(item["candle"]["open"], str)
            assert (
                client.get(f"/api/v1/decisions?symbol={symbol}&limit=1").json()["items"]
                == items[:1]
            )
        assert client.get("/api/v1/decisions").json()["symbol"] == "SPY"
        for query in ("symbol=NOPE", "timeframe=1m", "limit=0", "limit=201"):
            assert client.get(f"/api/v1/decisions?{query}").status_code == 422
        assert client.post("/api/v1/decisions").status_code == 405
        with patch("services.api.decisions_routes.check_database", return_value="down"):
            result = client.get("/api/v1/decisions")
            assert result.status_code == 503 and "items" not in result.json()
        with patch("services.api.decisions_routes.check_database", return_value="up"):
            with patch.object(
                engine, "connect", side_effect=OperationalError("secret", {}, Exception())
            ):
                result = client.get("/api/v1/decisions")
                assert result.status_code == 503 and "secret" not in result.text
    with engine.connect() as connection:
        assert connection.execute(select(risk_decisions)).all() == before


def test_decisions_empty(market: MarketFixture) -> None:
    settings, _, _, _ = market
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/decisions")
        assert response.status_code == 200 and response.json()["items"] == []


def test_reason_migration_preserves_graph_and_backfills_baseline(market: MarketFixture) -> None:
    _, engine, generator, _ = market
    store = MarketStore(
        engine, generator.spec.stream_id, strategy=BaseStrategy(), risk=RiskEngine()
    )
    for seq, close in enumerate(["101", "99", "100", "101"], start=1):
        store.append(
            replace(
                generator.next_closed(seq),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal(close),
            )
        )
    with engine.begin() as connection:
        last_id = store.history(1).candles[0].candle_id
        connection.execute(
            signals.update().where(signals.c.candle_id == last_id).values(strategy_version="legacy")
        )
        before = connection.execute(select(risk_decisions)).all()
        ids = set(connection.scalars(select(signals.c.signal_id)))
    config = Config("alembic.ini")
    command.downgrade(config, "0006_m15_integrity")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as connection:
        assert set(connection.scalars(select(signals.c.signal_id))) == ids
        assert connection.execute(select(risk_decisions)).all() == before
        reasons = set(connection.scalars(select(signals.c.reason)))
        assert reasons == {
            "Fechamento acima da abertura.",
            "Fechamento abaixo da abertura.",
            "Abertura e fechamento equivalentes. Sem ação.",
            "Justificativa histórica não registrada; regra não comprovada pelo backfill.",
        }
        assert connection.scalar(text("SELECT count(*) FROM candles")) == 4
        assert connection.scalar(text("SELECT count(*) FROM system_events")) == 4
