from ipaddress import ip_address
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

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


def require_local_stop(request: Request) -> None:
    """Non-secret STOP capability. Never reuse this policy for resume or execution."""
    try:
        local_peer = request.client is not None and ip_address(request.client.host).is_loopback
        local_host = request.url.hostname in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        local_peer, local_host = False, False
    if not local_peer or not local_host:
        raise HTTPException(403, "local_stop_only")
    if any(
        name in {"origin", "referer", "forwarded"}
        or name.startswith(("sec-fetch-", "x-forwarded-"))
        for name in request.headers
    ):
        raise HTTPException(403, "browser_or_proxy_control_forbidden")
    # Not a password: intentional native request; browser JS would need CORS preflight.
    if request.headers.get("x-paper-control") != "stop":
        raise HTTPException(403, "explicit_stop_required")


@router.post("/pause")
async def pause(request: Request, response: Response) -> dict[str, bool]:
    """Only local STOP. No body, secret, remote resume, reset, or order capability."""
    require_local_stop(request)
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(422, "stop_body_must_be_empty")
    try:
        store = PaperStore(request.app.state.database, request.app.state.configuration)
        await run_in_threadpool(store.set_paused, True)
    except SQLAlchemyError:
        raise HTTPException(503, "database_unavailable") from None
    except ValueError:
        raise HTTPException(503, "paper_reconciliation_failed") from None
    response.headers["Cache-Control"] = "no-store"
    return {"paused": True}
