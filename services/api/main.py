import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response

from packages.contracts.health import HealthResponse
from packages.domain.market import SimulationSpec
from services.api.config import Settings, get_settings
from services.api.database import check_database, create_database_engine
from services.api.market_routes import router as market_router
from services.api.market_store import MarketStore
from services.api.simulator_runtime import SimulatorRuntime
from services.market_simulator.generator import CandleGenerator

logger = logging.getLogger("trading_bot.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configuration = settings or get_settings()
        engine = create_database_engine(configuration)
        app.state.database = engine
        spec = SimulationSpec(configuration.simulator_seed, configuration.simulator_start)
        app.state.market = MarketStore(engine, spec.stream_id)
        app.state.simulator = SimulatorRuntime(
            configuration, app.state.market, CandleGenerator(spec)
        )
        app.state.simulator.start()
        try:
            yield
        finally:
            await app.state.simulator.stop()
            engine.dispose()

    app = FastAPI(title="Trading Bot Dashboard", version="0.1.0", lifespan=lifespan)
    app.include_router(market_router)

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
        simulator = request.app.state.simulator.status()
        ready = database == "up" and simulator.state == "running"
        response.status_code = 200 if ready else 503
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(
            status="ok" if ready else "degraded",
            database=database,
            checked_at=datetime.now(UTC),
            correlation_id=request.state.correlation_id,
            simulator=simulator,
        )

    return app


app = create_app()
