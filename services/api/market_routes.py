import asyncio
import logging
from dataclasses import asdict
from time import monotonic
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.market import MarketSnapshot
from services.api.database import check_database
from services.api.market_store import CursorReset, MarketStore
from services.api.simulator_runtime import SimulatorRuntime

router = APIRouter(prefix="/api/v1/market", tags=["market"])
logger = logging.getLogger("trading_bot.api")


@router.get("/candles", response_model=MarketSnapshot)
def history(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    after: Annotated[int | None, Query(ge=0)] = None,
    through: Annotated[int | None, Query(ge=0)] = None,
    stream_id: UUID | None = None,
    symbol: str | None = None,
    timeframe: str = "1h",
) -> MarketSnapshot:
    symbols = request.app.state.configuration.symbols
    selected = symbol or symbols[0]
    if selected not in symbols or timeframe != "1h":
        raise HTTPException(422, detail="unsupported_series")
    store: MarketStore = request.app.state.markets[selected]
    if stream_id is not None and stream_id != store.stream_id:
        raise HTTPException(409, detail="stream_changed")
    try:
        page = store.history(limit, after, through)
    except CursorReset as error:
        raise HTTPException(409, detail="cursor_reset_required") from error
    except SQLAlchemyError as error:
        raise HTTPException(503, detail="database_unavailable") from error
    return MarketSnapshot(
        stream_id=store.stream_id,
        symbol=selected,
        timeframe=timeframe,
        market_data=request.app.state.simulator.status(),
        correlation_id=request.state.correlation_id,
        **asdict(page),
    )


@router.websocket("/events")
async def events(
    websocket: WebSocket,
    stream_id: UUID,
    after: Annotated[int, Query(ge=0)] = 0,
    symbol: str | None = None,
    timeframe: str = "1h",
) -> None:
    origin = websocket.headers.get("origin")
    if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
        await websocket.close(code=1008, reason="local_origin_required")
        return
    stores: dict[str, MarketStore] = websocket.app.state.markets
    selected = symbol or next(
        (s for s, store in stores.items() if store.stream_id == stream_id), ""
    )
    if selected not in stores or timeframe != "1h":
        await websocket.close(code=1008, reason="unsupported_series")
        return
    store = stores[selected]
    runtime: SimulatorRuntime = websocket.app.state.simulator
    if stream_id != store.stream_id:
        await websocket.close(code=1008, reason="stream_changed")
        return
    await websocket.accept()
    cursor = after
    status_at = 0.0
    disconnected = asyncio.create_task(websocket.receive())
    try:
        # Verifica também cursor adiantado após reset do banco.
        await asyncio.to_thread(store.history, 1, cursor)
        while not disconnected.done():
            persisted = await asyncio.to_thread(store.events_after, cursor)
            for event in persisted:
                # Cada item foi lido de uma transação já commitada no PostgreSQL.
                await websocket.send_json(event.model_dump(mode="json"))
                cursor = event.sequence
            if monotonic() - status_at >= 2:
                database = await asyncio.to_thread(check_database, store.engine)
                simulator = runtime.status()
                await websocket.send_json(
                    {
                        "type": "stream.status",
                        "schema_version": "2.0",
                        "stream_id": str(store.stream_id),
                        "cursor": cursor,
                        "correlation_id": str(uuid4()),
                        "database": database,
                        "market_data": simulator.model_dump(mode="json"),
                    }
                )
                status_at = monotonic()
            await asyncio.sleep(0.2)
    except CursorReset:
        await websocket.close(code=1008, reason="cursor_reset_required")
    except SQLAlchemyError:
        await websocket.close(code=1013, reason="database_unavailable")
    except (WebSocketDisconnect, OSError):
        pass
    finally:
        disconnected.cancel()
        try:
            await disconnected
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
