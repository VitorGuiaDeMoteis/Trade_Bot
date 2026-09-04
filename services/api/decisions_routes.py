"""Queries only: never invokes engines or creates a trading command."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.decisions import (
    DecisionItem,
    DecisionsSnapshot,
    PaperDecisionResponse,
    RiskResponse,
    SignalResponse,
)
from packages.contracts.market import CandleResponse
from packages.contracts.paper import PaperFill, PaperOrder
from services.api.database import check_database
from services.api.market_store import MarketStore
from services.api.models import (
    candles,
    paper_fills,
    paper_orders,
    paper_outcomes,
    risk_decisions,
    signals,
)

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
        select(candles, signals, risk_decisions, paper_outcomes, paper_orders, paper_fills)
        .select_from(
            candles.join(signals)
            .join(risk_decisions)
            .outerjoin(
                paper_outcomes, paper_outcomes.c.risk_decision_id == risk_decisions.c.decision_id
            )
            .outerjoin(paper_orders, paper_orders.c.order_id == paper_outcomes.c.order_id)
            .outerjoin(paper_fills, paper_fills.c.order_id == paper_orders.c.order_id)
        )
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
            from services.api.models import system_controls

            active_run_id = connection.scalar(select(system_controls.c.active_run_id))
            items = []
            for row in connection.execute(query).mappings():
                if row[paper_outcomes.c.status] is not None:
                    order = (
                        PaperOrder.model_validate({c.name: row[c] for c in paper_orders.c})
                        if row[paper_orders.c.order_id] is not None
                        else None
                    )
                    fill = (
                        PaperFill.model_validate({c.name: row[c] for c in paper_fills.c})
                        if row[paper_fills.c.fill_id] is not None
                        else None
                    )
                    paper_resp = PaperDecisionResponse(
                        status=row[paper_outcomes.c.status],
                        run_id=row[paper_outcomes.c.run_id],
                        order=order,
                        fill=fill,
                    )
                else:
                    paper_resp = PaperDecisionResponse(status="WAITING", run_id=active_run_id)

                items.append(
                    DecisionItem(
                        candle=CandleResponse.model_validate({c.name: row[c] for c in candles.c}),
                        signal=SignalResponse.model_validate({c.name: row[c] for c in signals.c}),
                        risk=RiskResponse.model_validate(
                            {c.name: row[c] for c in risk_decisions.c}
                        ),
                        paper=paper_resp,
                    )
                )
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
