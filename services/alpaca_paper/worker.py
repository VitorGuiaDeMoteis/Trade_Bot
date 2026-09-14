import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, select

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.executor import AlpacaPaperExecutor
from services.api.config import Settings
from services.api.models import (
    broker_portfolio_snapshots,
    broker_positions,
    candles,
    paper_orders,
    risk_decisions,
    signals,
    system_controls,
)

logger = logging.getLogger("trading_bot.alpaca_worker")


class AlpacaPaperWorker:
    def __init__(self, engine: Engine, adapter: AlpacaPaperAdapter, settings: Settings) -> None:
        self.engine = engine
        self.adapter = adapter
        self.settings = settings
        self.executor = AlpacaPaperExecutor(adapter)
        self.task: asyncio.Task[None] | None = None
        self.running = False
        self.degraded = False

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.running = True
            self.task = asyncio.create_task(self._run(), name="alpaca-paper-worker")

    async def stop(self) -> None:
        self.running = False
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def preflight(self) -> bool:
        try:
            account = await self.adapter.get_account()
            if account.get("status") != "ACTIVE":
                logger.error(f"Alpaca account is not active: {account.get('status')}")
                return False
            return True
        except Exception as e:
            logger.error(f"Alpaca preflight failed: {e}")
            return False

    async def _run(self) -> None:
        async with self.adapter:
            if not await self.preflight():
                self.degraded = True

            try:
                await self._reconcile_active_orders()
            except Exception as e:
                logger.error(f"Initial reconciliation failed: {e}")
                self.degraded = True

            while self.running:
                try:
                    if not self.degraded:
                        await self._process_pending_submits()
                    await self._reconcile_active_orders()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Worker iteration error: {e}")
                await self._snapshot_broker_portfolio()
                await asyncio.sleep(3.0)

    async def _process_pending_submits(self) -> None:
        def fetch_pending() -> list[dict[str, Any]] | None:
            with self.engine.connect() as c:
                control = c.execute(select(system_controls)).mappings().first()
                if not control or control["paused"]:
                    return None
                run_id = control["active_run_id"]
                if not run_id:
                    return None

                query = (
                    select(risk_decisions, signals, candles.c.symbol)
                    .join(signals, risk_decisions.c.signal_id == signals.c.signal_id)
                    .join(candles, signals.c.candle_id == candles.c.candle_id)
                    .outerjoin(
                        paper_orders,
                        paper_orders.c.risk_decision_id == risk_decisions.c.decision_id,
                    )
                    .where(
                        risk_decisions.c.decision == "APPROVED", paper_orders.c.order_id.is_(None)
                    )
                    .order_by(risk_decisions.c.decided_at)
                    .limit(10)
                )
                return [{"run_id": run_id, **dict(row)} for row in c.execute(query).mappings()]

        pending = await asyncio.to_thread(fetch_pending)
        print(f"PENDING: {pending}")
        if not pending:
            return

        for row in pending:
            run_id = row["run_id"]
            risk = RiskDecision(
                decision_id=row["decision_id"],
                signal_id=row["signal_id"],
                decision=row["decision"],
                reason=row["reason"],
                decided_at=row["decided_at"],
            )
            symbol = row["symbol"]
            side = row["signal_type"]
            quantity = 0
            notional = Decimal("10.00")
            order_id = uuid5(run_id, str(risk.decision_id))

            try:
                with self.engine.begin() as conn:
                    await self.executor.submit(
                        connection=conn,
                        run_id=run_id,
                        signal_id=row["signal_id"],
                        risk=risk,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        order_id=order_id,
                        requested_at=datetime.now(UTC),
                        notional=notional,
                    )
            except Exception as e:
                logger.error(f"Error submitting order {order_id}: {e}")

    
    async def _snapshot_broker_portfolio(self) -> None:
        try:
            account = await self.adapter.get_account()
            remote_positions = await self.adapter._request("GET", "/positions")
            
            cash = Decimal(account.get("cash", "0"))
            equity = Decimal(account.get("equity", "0"))
            market_value = Decimal(account.get("portfolio_value", "0")) - cash
            buying_power = Decimal(account.get("buying_power", "0"))
            
            positions_data = []
            for rp in remote_positions:
                positions_data.append({
                    "provider": "alpaca",
                    "symbol": rp.get("symbol", ""),
                    "quantity": Decimal(rp.get("qty", "0")),
                    "average_price": Decimal(rp.get("avg_entry_price", "0")),
                    "current_price": Decimal(rp.get("current_price", "0")),
                    "market_value": Decimal(rp.get("market_value", "0")),
                    "unrealized_pnl": Decimal(rp.get("unrealized_pl", "0")),
                    "updated_at": datetime.now(UTC),
                })
            
            status = "ACTIVE"
            self.degraded = False
        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            self.degraded = True
            status = "DEGRADED"
            # Fallback to update just status if we can't fetch anything?
            # But the requirement says: "Se a última reconciliação estiver velha ou houver falha da Alpaca: retornar o último snapshot conhecido; marcar claramente DEGRADED / STALE; informar last_reconciled_at"
            # If we fail, we just update the status of the existing snapshot to DEGRADED
            try:
                def update_status_degraded() -> None:
                    with self.engine.begin() as conn:
                        from sqlalchemy import update
                        conn.execute(
                            update(broker_portfolio_snapshots)
                            .where(broker_portfolio_snapshots.c.provider == "alpaca")
                            .values(status="DEGRADED")
                        )
                await asyncio.to_thread(update_status_degraded)
            except Exception as inner_e:
                logger.error(f"Failed to update snapshot status: {inner_e}")
            return

        def save_snapshot() -> None:
            with self.engine.begin() as conn:
                from sqlalchemy import delete
                from sqlalchemy.dialects.postgresql import insert
                
                stmt = insert(broker_portfolio_snapshots).values(
                    provider="alpaca",
                    status=status,
                    cash=cash,
                    market_value=market_value,
                    equity=equity,
                    unrealized_pnl=Decimal("0"), # or compute from pos
                    buying_power=buying_power,
                    last_reconciled_at=datetime.now(UTC)
                )
                upsert = stmt.on_conflict_do_update(
                    index_elements=['provider'],
                    set_={
                        'status': status,
                        'cash': cash,
                        'market_value': market_value,
                        'equity': equity,
                        'unrealized_pnl': stmt.excluded.unrealized_pnl,
                        'buying_power': buying_power,
                        'last_reconciled_at': stmt.excluded.last_reconciled_at
                    }
                )
                conn.execute(upsert)
                
                # Replace positions for alpaca
                conn.execute(delete(broker_positions).where(broker_positions.c.provider == "alpaca"))
                if positions_data:
                    conn.execute(insert(broker_positions), positions_data)
                    
        await asyncio.to_thread(save_snapshot)

    async def _reconcile_active_orders(self) -> None:
        def fetch_active() -> list[UUID]:
            with self.engine.connect() as c:
                query = select(paper_orders.c.order_id).where(
                    paper_orders.c.status.in_(
                        [
                            "SUBMITTING",
                            "NEW",
                            "ACCEPTED",
                            "PENDING_NEW",
                            "PARTIALLY_FILLED",
                            "PENDING_CANCEL",
                            "REPLACED",
                            "UNKNOWN",
                        ]
                    )
                )
                return list(c.scalars(query).all())

        active_orders = await asyncio.to_thread(fetch_active)
        for order_id in active_orders:
            try:
                with self.engine.begin() as conn:
                    await self.executor.reconcile_order(conn, order_id)
            except Exception as e:
                logger.error(f"Error reconciling order {order_id}: {e}")
