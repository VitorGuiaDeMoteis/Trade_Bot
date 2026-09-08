import asyncio
from datetime import datetime, timezone
import logging
from uuid import UUID
import uuid

from packages.domain.risk import RiskDecision
from services.paper_executor.broker import ExecutionBroker
from services.api.market_store import MarketStore
from packages.domain.paper import PaperResult
from sqlalchemy import text
from decimal import Decimal

logger = logging.getLogger("live_paper_runtime")


class LivePaperExecutionRuntime:
    def __init__(self, broker: ExecutionBroker, store: MarketStore, engine, symbol: str):
        self.broker = broker
        self.store = store
        self.engine = engine
        self.symbol = symbol
        self.running = False
        self._task = None

    def start(self):
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        try:
            await self._reconcile()
        except Exception as e:
            logger.error(f"Failed to reconcile on startup: {e}")
            return

        while self.running:
            try:
                await self._process_pending()
            except Exception as e:
                logger.error(f"Error processing pending decisions: {e}")
            await asyncio.sleep(5)

    async def _reconcile(self):
        account = await self.broker.get_account()
        orders = await self.broker.get_orders()

    async def _process_pending(self):
        query = text("""
            SELECT r.decision_id, r.signal_id, r.decision, r.reason, r.decided_at,
                   s.signal_type, s.strategy_version, s.stream_id, c.close as reference_price
            FROM risk_decisions r
            JOIN strategy_signals s ON r.signal_id = s.signal_id
            JOIN candles c ON s.candle_id = c.candle_id
            LEFT JOIN broker_orders b ON r.decision_id = b.risk_decision_id
            WHERE b.client_order_id IS NULL 
              AND r.decision = 'APPROVED'
              AND s.signal_type != 'HOLD'
              AND c.symbol = :symbol
              AND c.timeframe = '15m'
        """)

        with self.engine.begin() as conn:
            rows = conn.execute(query, {"symbol": self.symbol}).fetchall()

        for row in rows:
            decision = RiskDecision(
                decision_id=row.decision_id,
                signal_id=row.signal_id,
                decision=row.decision,
                reason=row.reason,
                decided_at=row.decided_at.replace(tzinfo=timezone.utc),
            )
            client_order_id = f"agy-{decision.decision_id}-{decision.signal_id}"

            # Check if order exists in broker (timeout recovery)
            remote_order = await self.broker.get_order_by_client_order_id(client_order_id)
            if remote_order:
                # Persist remote order
                self._persist_order(row, client_order_id, remote_order)
                continue

            # Submit to broker
            try:
                # Calculate size (stubbed for v0.1 as per instructions, 10% equity approx)
                qty = 1  # We'd fetch account equity here
                result = await self.broker.execute(
                    book=None,
                    symbol=self.symbol,
                    side=row.signal_type,
                    reference=Decimal(row.reference_price),
                    quantity=qty,
                    risk=decision,
                )

                # Assume status from execution
                status = "submitted" if result.status == "SUBMITTED" else "rejected"

                # Persist to local audit
                self._persist_order(
                    row, client_order_id, {"id": None, "status": status, "qty": qty}
                )

            except Exception as e:
                logger.error(f"Failed to execute order {client_order_id}: {e}")

    def _persist_order(self, row, client_order_id, remote_order):
        with self.engine.begin() as t_conn:
            t_conn.execute(
                text("""
                INSERT INTO broker_orders (
                    client_order_id, broker_order_id, signal_id, risk_decision_id,
                    strategy_version, symbol, timeframe, side, requested_qty,
                    status, submitted_at, last_reconciliation_at
                ) VALUES (
                    :cid, :bid, :sid, :rid, :sv, :sym, :tf, :side, :qty, :status, :now, :now
                ) ON CONFLICT DO NOTHING
            """),
                {
                    "cid": client_order_id,
                    "bid": remote_order.get("id"),
                    "sid": row.signal_id,
                    "rid": row.decision_id,
                    "sv": row.strategy_version,
                    "sym": self.symbol,
                    "tf": "15m",
                    "side": row.signal_type,
                    "qty": remote_order.get("qty", 1) or 1,
                    "status": remote_order.get("status", "submitted"),
                    "now": datetime.now(timezone.utc),
                },
            )
