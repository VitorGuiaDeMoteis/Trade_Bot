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

    from sqlalchemy import text

    engine = request.app.state.database

    with engine.begin() as conn:
        ctrl = conn.execute(
            text("SELECT armed FROM live_paper_control WHERE control_id = 1")
        ).fetchone()
        armed = ctrl.armed if ctrl else False

        last_sig = conn.execute(
            text(
                "SELECT r.decision_id, r.signal_id, r.decision, s.signal_type "
                "FROM risk_decisions r "
                "JOIN signals s ON r.signal_id = s.signal_id "
                "WHERE s.timeframe = '15m' "
                "ORDER BY r.decided_at DESC LIMIT 1"
            )
        ).fetchone()
        latest_decision = (
            {
                "decision_id": str(last_sig.decision_id),
                "signal_id": str(last_sig.signal_id),
                "decision": last_sig.decision,
                "signal_type": last_sig.signal_type,
            }
            if last_sig
            else None
        )

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
            "currency": account.currency,
            "equity": str(account.equity),
            "cash": str(account.cash),
            "buying_power": str(account.buying_power),
            "day_pnl": None,
            "total_pnl": None,
        }
        positions = [
            {
                "symbol": p.symbol,
                "quantity": int(p.quantity),
                "average_price": str(p.average_entry_price),
                "current_price": str(p.current_price),
                "market_value": None,
                "unrealized_pnl": None,
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
        risk={"paused": not armed, "degraded": False, "reason": None},
        latest_decision=latest_decision,
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
            rows = conn.execute(
                text("SELECT fill_id, client_order_id, qty, price, filled_at FROM broker_fills")
            ).fetchall()
            return {"items": [dict(r._mapping) for r in rows]}
    except Exception as e:
        import logging

        logging.getLogger("live_paper_routes").error(f"Fills database error: {e}")
        raise HTTPException(503, "database_unavailable") from None
