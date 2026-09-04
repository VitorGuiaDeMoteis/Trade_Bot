"""Queries only: never invokes engines or creates a trading command."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.decisions import (
    DecisionItem,
    DecisionsSnapshot,
    RiskResponse,
    SignalResponse,
)
from packages.contracts.market import CandleResponse
from services.api.database import check_database
from services.api.market_store import MarketStore
from services.api.models import candles, risk_decisions, signals

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("", response_model=DecisionsSnapshot)
def decisions(
    request: Request,
    response: Response,
    symbol: str | None = None,
    timeframe: str = "1h",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DecisionsSnapshot:
    configuration = request.app.state.configuration
    selected = symbol or configuration.symbols[0]
    if selected not in configuration.symbols or timeframe != "1h":
        raise HTTPException(422, detail="unsupported_series")
    store: MarketStore = request.app.state.markets[selected]
    if check_database(store.engine) != "up":
        raise HTTPException(503, detail="database_unavailable")
    query = (
        select(candles, signals, risk_decisions)
        .select_from(candles.join(signals).join(risk_decisions))
        .where(
            candles.c.stream_id == store.stream_id,
            candles.c.symbol == selected,
            candles.c.timeframe == timeframe,
            candles.c.is_closed.is_(True),
        )
        .order_by(candles.c.open_time.desc(), signals.c.signal_id.desc())
        .limit(limit)
    )
    try:
        with store.engine.connect() as connection:
            items = [
                DecisionItem(
                    candle=CandleResponse.model_validate({c.name: row[c] for c in candles.c}),
                    signal=SignalResponse.model_validate({c.name: row[c] for c in signals.c}),
                    risk=RiskResponse.model_validate({c.name: row[c] for c in risk_decisions.c}),
                )
                for row in connection.execute(query).mappings()
            ]
    except SQLAlchemyError:
        raise HTTPException(503, detail="database_unavailable") from None
    response.headers["Cache-Control"] = "no-store"
    return DecisionsSnapshot(
        symbol=selected,
        symbols=configuration.symbols,
        items=items,
        limit=limit,
        market_data=request.app.state.simulator.status(),
        correlation_id=request.state.correlation_id,
    )
