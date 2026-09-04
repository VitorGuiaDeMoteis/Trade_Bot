import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.paper import (
    PaperFillsPage,
    PaperOrdersPage,
    PaperPortfolio,
    PaperPositionsPage,
)
from services.api.database import check_database
from services.api.paper_queries import portfolio
from services.api.paper_store import PaperStore

router = APIRouter(prefix="/api/v1/paper", tags=["local paper"])


def read_portfolio(request: Request, response: Response, limit: int = 50) -> PaperPortfolio:
    engine = request.app.state.database
    if check_database(engine) != "up":
        raise HTTPException(503, "database_unavailable")
    response.headers["Cache-Control"] = "no-store"
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c, c.begin():
            return portfolio(c, PaperStore(engine, request.app.state.configuration), limit)
    except SQLAlchemyError:
        raise HTTPException(503, "database_unavailable") from None
    except ValueError:
        raise HTTPException(503, "paper_reconciliation_failed") from None


@router.get("/portfolio", response_model=PaperPortfolio)
def get_portfolio(request: Request, response: Response) -> PaperPortfolio:
    return read_portfolio(request, response)


@router.get("/positions", response_model=PaperPositionsPage)
def get_positions(request: Request, response: Response) -> PaperPositionsPage:
    p = read_portfolio(request, response)
    return PaperPositionsPage(run_id=p.run_id, step=p.step, items=p.positions)


@router.get("/orders", response_model=PaperOrdersPage)
def get_orders(
    request: Request, response: Response, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> PaperOrdersPage:
    p = read_portfolio(request, response, limit)
    return PaperOrdersPage(run_id=p.run_id, step=p.step, items=p.orders)


@router.get("/fills", response_model=PaperFillsPage)
def get_fills(
    request: Request, response: Response, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> PaperFillsPage:
    p = read_portfolio(request, response, limit)
    return PaperFillsPage(run_id=p.run_id, step=p.step, items=p.fills)


@router.post("/pause")
def pause(
    request: Request, response: Response, authorization: Annotated[str | None, Header()] = None
) -> dict[str, bool]:
    """Only capability exposed to the app: stop. Resume/reset stay on local CLI."""
    token = request.app.state.configuration.paper_control_token
    if not token or len(token.get_secret_value()) < 32:
        raise HTTPException(503, "paper_control_not_configured")
    expected = "Bearer " + token.get_secret_value()
    if not authorization or not secrets.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401, "invalid_paper_control_token")
    # Browser origins are never allowed to issue local commands.
    if request.headers.get("origin"):
        raise HTTPException(403, "browser_control_forbidden")
    try:
        PaperStore(request.app.state.database, request.app.state.configuration).set_paused(True)
    except SQLAlchemyError:
        raise HTTPException(503, "database_unavailable") from None
    response.headers["Cache-Control"] = "no-store"
    return {"paused": True}
