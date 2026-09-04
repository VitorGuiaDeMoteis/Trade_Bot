import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response

from packages.contracts.health import HealthResponse
from packages.contracts.provider import MarketDataProvider
from packages.domain.market import SimulationSpec
from packages.domain.market_bar import series_id
from services.api.backtest_routes import router as backtest_router
from services.api.config import Settings, get_settings
from services.api.database import check_database, create_database_engine
from services.api.decisions_routes import router as decisions_router
from services.api.market_routes import router as market_router
from services.api.market_store import MarketStore
from services.api.paper_routes import router as paper_router
from services.api.simulator_runtime import SimulatorRuntime
from services.market_data.alpaca_provider import AlpacaMarketDataProvider
from services.market_data.simulator import SimulatorMarketDataProvider
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import BaseStrategy

logger = logging.getLogger("trading_bot.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configuration = settings or get_settings()
        engine = create_database_engine(configuration)
        app.state.database = engine
        spec = SimulationSpec(configuration.simulator_seed, configuration.simulator_start)
        provider: MarketDataProvider
        if configuration.market_data_provider == "alpaca":
            assert configuration.alpaca_api_key_id and configuration.alpaca_api_secret_key
            provider = AlpacaMarketDataProvider(
                api_key=configuration.alpaca_api_key_id.get_secret_value(),
                secret_key=configuration.alpaca_api_secret_key.get_secret_value(),
                feed=configuration.alpaca_data_feed,
                symbols=configuration.symbols,
                timeframe=configuration.market_timeframe,
            )
        else:
            provider = SimulatorMarketDataProvider(spec, configuration.simulator_interval_seconds)
        stores = {
            symbol: MarketStore(
                engine,
                spec.stream_id
                if configuration.market_data_provider == "simulator"
                else series_id("alpaca", symbol, configuration.market_timeframe),
                strategy=BaseStrategy(),
                risk=RiskEngine(),
            )
            for symbol in configuration.symbols
        }
        app.state.markets = stores
        app.state.configuration = configuration
        app.state.market = stores[configuration.symbols[0]]
        app.state.simulator = SimulatorRuntime(configuration, app.state.market, provider, stores)
        app.state.simulator.start()
        try:
            yield
        finally:
            await app.state.simulator.stop()
            engine.dispose()

    app = FastAPI(title="Trading Bot Dashboard", version="0.1.0", lifespan=lifespan)
    app.include_router(market_router)
    app.include_router(decisions_router)
    app.include_router(paper_router)
    app.include_router(backtest_router)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            correlation_id = UUID(request.headers.get("X-Correlation-ID", ""))
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = correlation_id
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        logger.info(
            json.dumps(
                {
                    "event": "http.request.completed",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "correlation_id": str(correlation_id),
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000),
                }
            )
        )
        return response

    @app.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
    def health(request: Request, response: Response) -> HealthResponse:
        database = check_database(request.app.state.database)
        provider_status = request.app.state.simulator.status()
        state = provider_status.state
        ready = database == "up" and state in {"connected", "market_closed"}
        response.status_code = 200 if ready else 503
        response.headers["Cache-Control"] = "no-store"

        mode = (
            "DADOS REAIS / EXECUÇÃO SIMULADA"
            if provider_status.provider != "simulator"
            else "SIMULADO"
        )

        return HealthResponse(
            status="ok" if ready else "degraded",
            mode=mode,
            database=database,
            checked_at=datetime.now(UTC),
            correlation_id=request.state.correlation_id,
            market_data=provider_status,
        )

    return app


app = create_app()
