from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid5, NAMESPACE_URL

from fastapi import APIRouter, HTTPException, Request, Response

from packages.contracts.paper import PaperFill, PaperOrder, PaperPortfolio, PaperPositionResponse
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.models import system_controls

router = APIRouter(prefix="/api/v1/broker", tags=["broker paper"])

@router.get("/portfolio", response_model=PaperPortfolio)
async def get_broker_portfolio(request: Request, response: Response) -> PaperPortfolio:
    config = request.app.state.configuration
    if getattr(config, "execution_mode", "") != "alpaca_paper":
        raise HTTPException(400, "not_in_alpaca_paper_mode")

    api_key = config.alpaca_api_key_id.get_secret_value() if config.alpaca_api_key_id else ""
    secret_key = config.alpaca_api_secret_key.get_secret_value() if config.alpaca_api_secret_key else ""
    
    engine = request.app.state.database
    with engine.begin() as conn:
        control = conn.execute(system_controls.select()).mappings().first()
        paused = control["paused"] if control else False
        run_id = control["active_run_id"] if control else None
        
    try:
        async with AlpacaPaperAdapter(api_key, secret_key) as adapter:
            account = await adapter.get_account()
            remote_positions = await adapter._request("GET", "/positions")
            remote_orders = await adapter._request("GET", "/orders", params={"status": "all", "limit": 100})
            remote_fills = await adapter._request("GET", "/account/activities/FILL")
            
            cash = Decimal(account.get("cash", "0"))
            equity = Decimal(account.get("equity", "0"))
            market_value = Decimal(account.get("portfolio_value", "0")) - cash
            status = account.get("status", "UNKNOWN")
            
            positions = []
            for rp in remote_positions:
                positions.append(PaperPositionResponse(
                    symbol=rp.get("symbol", ""),
                    quantity=Decimal(rp.get("qty", "0")), # type: ignore
                    average_price=Decimal(rp.get("avg_entry_price", "0")),
                    current_price=Decimal(rp.get("current_price", "0")),
                    market_value=Decimal(rp.get("market_value", "0")),
                    realized_pnl=Decimal("0"),
                    unrealized_pnl=Decimal(rp.get("unrealized_pl", "0")),
                    updated_at=datetime.now(UTC),
                ))
                
            orders = []
            for ro in remote_orders:
                qty = Decimal(ro.get("qty", "0")) if ro.get("qty") else Decimal(ro.get("notional", "0"))
                filled_qty = Decimal(ro.get("filled_qty", "0"))
                orders.append(PaperOrder(
                    order_id=uuid5(NAMESPACE_URL, ro.get("id", "")),
                    run_id=run_id or uuid5(NAMESPACE_URL, "dummy"),
                    signal_id=uuid5(NAMESPACE_URL, "dummy"),
                    risk_decision_id=uuid5(NAMESPACE_URL, "dummy"),
                    symbol=ro.get("symbol", ""),
                    side=ro.get("side", "").upper() if ro.get("side") else "BUY",
                    quantity=qty, # type: ignore
                    filled_quantity=filled_qty, # type: ignore
                    status=ro.get("status", "").upper(),
                    requested_at=datetime.fromisoformat(ro.get("created_at", datetime.now(UTC).isoformat()).replace("Z", "+00:00")),
                    idempotency_key=uuid5(NAMESPACE_URL, ro.get("client_order_id", "")),
                    reason=f"Broker ID: {ro.get('id', '')}",
                    client_order_id=ro.get("client_order_id", ""),
                    broker_order_id=ro.get("id", ""),
                    broker_status=ro.get("status", ""),
                ))
                
            fills = []
            for rf in remote_fills:
                fills.append(PaperFill(
                    fill_id=uuid5(NAMESPACE_URL, rf.get("id", "")),
                    order_id=uuid5(NAMESPACE_URL, rf.get("order_id", "")),
                    broker_fill_id=rf.get("id", ""),
                    price=Decimal(rf.get("price", "0")),
                    reference_price=Decimal(rf.get("price", "0")),
                    quantity=Decimal(rf.get("qty", "0")), # type: ignore
                    fee=Decimal("0"),
                    slippage=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    filled_at=datetime.fromisoformat(rf.get("transaction_time", datetime.now(UTC).isoformat()).replace("Z", "+00:00")),
                ))
            
            return PaperPortfolio(
                run_id=run_id,
                status=status,
                provider="alpaca",
                paused=paused,
                as_of=datetime.now(UTC),
                initial_cash=cash,
                cash=cash,
                market_value=market_value,
                equity=equity,
                total_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
                fees=Decimal("0"),
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
                positions=positions,
                orders=orders,
                fills=fills,
            )
    except Exception as e:
        raise HTTPException(502, f"broker_error: {e}")
