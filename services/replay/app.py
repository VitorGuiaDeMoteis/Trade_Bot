"""Standalone FastAPI replay process: no imports of the trading app or broker runtime."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Response

from packages.domain.backtest import Dataset
from packages.domain.paper import PaperConfig
from services.api.mission_control import router
from services.backtesting.artifacts import load_manifest
from services.replay.runtime import ReplayRuntime

DEFAULT_DATASET = Path(__file__).with_name("data") / "spy-history.json"


def create_replay_app(
    dataset: Dataset | None = None,
    config: PaperConfig | None = None,
    *,
    speed: float = 1,
    source: str = "SPY · histórico local 1h",
    autostart: bool = True,
) -> FastAPI:
    if dataset is None:
        dataset, defaults = load_manifest(DEFAULT_DATASET)
        config = config or defaults
    replay = ReplayRuntime(dataset, config or PaperConfig(), speed=speed, source=source)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if autostart:
            replay.start()
        try:
            yield
        finally:
            await replay.stop()

    app = FastAPI(title="Trade Bot Historical Replay", lifespan=lifespan)
    app.state.replay = replay
    app.state.mission_control_mode = "replay"
    app.include_router(router)

    @app.get("/health")
    async def health(response: Response) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 503 if replay.status == "ERROR" else 200
        return {
            "mode": "REPLAY",
            "status": "degraded" if replay.status == "ERROR" else "ok",
            "replay_status": replay.status,
            "database": "not_used",
        }

    @app.get("/api/v1/replay/state")
    async def state(response: Response, after: int = Query(default=0, ge=0)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return replay.snapshot(after)

    return app
