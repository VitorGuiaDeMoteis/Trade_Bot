from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from packages.contracts.market import MarketDataStatus
from services.paper_executor.alpaca import AlpacaPaperBroker

router = APIRouter(prefix="/api/v1/live-paper", tags=["live-paper"])


class DashboardResponse(BaseModel):
    schema_version: str = "1.0"
    mode: str
    simulated_money: bool = True
    broker: dict[str, Any]
    market: dict[str, Any]
    account: dict[str, Any]
    risk: dict[str, Any]
    latest_decision: dict[str, Any] | None
    positions: list[dict[str, Any]]
    updated_at: datetime


@router.get("/dashboard")
async def dashboard(request: Request) -> DashboardResponse:
    settings = request.app.state.configuration
    market_status: MarketDataStatus = request.app.state.simulator.status()
    mode = "ALPACA_PAPER" if settings.execution_mode == "alpaca_paper" else "LOCAL_PAPER"

    if settings.execution_mode == "alpaca_paper":
        if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
            raise HTTPException(503, "ALPACA PAPER CREDENTIALS PENDING")
        executor = AlpacaPaperBroker(
            settings.alpaca_api_key_id.get_secret_value(),
            settings.alpaca_api_secret_key.get_secret_value(),
        )
        try:
            account = await executor.get_account()
            positions_data = await executor.get_positions()
        except Exception:
            raise HTTPException(503, "broker_unavailable") from None

        account_data = {
            "currency": account.get("currency", "USD"),
            "equity": account.get("equity", "0"),
            "cash": account.get("cash", "0"),
            "buying_power": account.get("buying_power", "0"),
            "day_pnl": None,
            "total_pnl": None,
        }
        positions = [
            {
                "symbol": p["symbol"],
                "quantity": int(p["qty"]),
                "average_price": p["avg_entry_price"],
                "current_price": p["current_price"],
                "market_value": p["market_value"],
                "unrealized_pnl": p["unrealized_pl"],
            }
            for p in positions_data
        ]
        broker = {
            "name": "alpaca",
            "connected": True,
            "last_sync_utc": datetime.now(UTC).isoformat(),
            "degraded_reason": None,
        }
    else:
        account_data = {
            "currency": "USD",
            "equity": "10000.00",
            "cash": "10000.00",
            "buying_power": "10000.00",
            "day_pnl": None,
            "total_pnl": None,
        }
        positions = []
        broker = {
            "name": "local",
            "connected": True,
            "last_sync_utc": datetime.now(UTC).isoformat(),
            "degraded_reason": None,
        }

    return DashboardResponse(
        mode=mode,
        broker=broker,
        market={
            "status": "OPEN" if market_status.state != "market_closed" else "CLOSED",
            "provider": market_status.provider or "simulator",
            "feed": market_status.feed or "local",
            "last_bar_utc": market_status.last_bar_at.isoformat()
            if market_status.last_bar_at
            else None,
            "operational_timeframe": settings.market_timeframe,
        },
        account=account_data,
        risk={"paused": False, "degraded": False, "reason": None},
        latest_decision=None,
        positions=positions,
        updated_at=datetime.now(UTC),
    )


@router.get("/orders")
async def orders(request: Request) -> dict[str, Any]:
    settings = request.app.state.configuration
    if settings.execution_mode == "alpaca_paper":
        if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
            raise HTTPException(503, "ALPACA PAPER CREDENTIALS PENDING")
        executor = AlpacaPaperBroker(
            settings.alpaca_api_key_id.get_secret_value(),
            settings.alpaca_api_secret_key.get_secret_value(),
        )
        try:
            orders_data = await executor.get_orders()
        except Exception:
            raise HTTPException(503, "broker_unavailable") from None
        return {"items": orders_data}
    return {"items": []}


@router.get("/fills")
async def fills(request: Request) -> dict[str, Any]:
    from sqlalchemy import text
    engine = request.app.state.database
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT fill_id, client_order_id, qty, price, filled_at FROM broker_fills")).fetchall()
            return {"items": [dict(r._mapping) for r in rows]}
    except Exception as e:
        raise HTTPException(503, f"database_error: {e}")
