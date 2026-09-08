import sys
content = '''import asyncio
from datetime import datetime, timezone
import logging
from uuid import UUID
from decimal import Decimal

from packages.domain.risk import RiskDecision
from services.paper_executor.broker import ExternalBroker, BrokerOrder
from sqlalchemy import text

logger = logging.getLogger("live_paper_runtime")

class LivePaperExecutionRuntime:
    def __init__(self, broker: ExternalBroker, engine, symbol: str):
        self.broker = broker
        self.engine = engine
        self.symbol = symbol
        self.running = False
        self._task = None
        self.execution_ready = False

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
            self.execution_ready = True
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
        clock = await self.broker.get_clock()
        positions = await self.broker.get_positions()
        
    async def _process_pending(self):
        if not self.execution_ready:
            return
            
        clock = await self.broker.get_clock()
        if not clock.get("is_open", False):
            return

        query = text("""
            SELECT r.decision_id, r.signal_id, r.decision, r.reason, r.decided_at,
                   s.signal_type, s.strategy_version, c.close as reference_price
            FROM risk_decisions r
            JOIN signals s ON r.signal_id = s.signal_id
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
            
        if not rows:
            return
            
        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        
        current_qty = 0
        for p in positions:
            if p.symbol == self.symbol:
                current_qty = p.quantity
                break
            
        for row in rows:
            decision_id = row.decision_id
            signal_id = row.signal_id
            client_order_id = f"agy-{decision_id}-{signal_id}"
            
            remote_order = await self.broker.get_order_by_client_order_id(client_order_id)
            if remote_order:
                self._persist_order(row, remote_order)
                continue
            
            # Position sizing
            qty = 0
            if row.signal_type == "BUY":
                if current_qty > 0:
                    continue
                max_cash = account.equity * Decimal("0.10")
                ref_price = Decimal(row.reference_price)
                if ref_price > 0:
                    qty = int(max_cash // ref_price)
            elif row.signal_type == "SELL":
                if current_qty <= 0:
                    continue
                qty = current_qty

            if qty <= 0:
                self._persist_failed_order(row, client_order_id, "rejected_sizing")
                continue
                
            try:
                order = await self.broker.submit_order(
                    symbol=self.symbol,
                    side=row.signal_type,
                    quantity=qty,
                    client_order_id=client_order_id
                )
                self._persist_order(row, order)
            except Exception as e:
                logger.error(f"Order failed {client_order_id}: {e}")

    def _persist_order(self, row, order: BrokerOrder):
        with self.engine.begin() as t_conn:
            t_conn.execute(text("""
                INSERT INTO broker_orders (
                    client_order_id, broker_order_id, signal_id, risk_decision_id,
                    strategy_version, symbol, timeframe, side, requested_qty,
                    status, filled_qty, filled_avg_price, submitted_at, last_reconciliation_at
                ) VALUES (
                    :cid, :bid, :sid, :rid, :sv, :sym, :tf, :side, :rq, :st, :fq, :fap, :sub, :now
                ) ON CONFLICT (client_order_id) DO UPDATE SET
                    broker_order_id = EXCLUDED.broker_order_id,
                    status = EXCLUDED.status,
                    filled_qty = EXCLUDED.filled_qty,
                    filled_avg_price = EXCLUDED.filled_avg_price,
                    last_reconciliation_at = EXCLUDED.last_reconciliation_at
            """), {
                "cid": order.client_order_id,
                "bid": order.broker_order_id,
                "sid": row.signal_id,
                "rid": row.decision_id,
                "sv": row.strategy_version,
                "sym": self.symbol,
                "tf": "15m",
                "side": row.signal_type,
                "rq": order.requested_qty,
                "st": order.status,
                "fq": order.filled_qty,
                "fap": order.filled_avg_price,
                "sub": order.submitted_at,
                "now": datetime.now(timezone.utc)
            })

    def _persist_failed_order(self, row, client_order_id: str, reason: str):
        with self.engine.begin() as t_conn:
            t_conn.execute(text("""
                INSERT INTO broker_orders (
                    client_order_id, broker_order_id, signal_id, risk_decision_id,
                    strategy_version, symbol, timeframe, side, requested_qty,
                    status, filled_qty, filled_avg_price, submitted_at, last_reconciliation_at
                ) VALUES (
                    :cid, NULL, :sid, :rid, :sv, :sym, :tf, :side, 0, :st, 0, 0, :now, :now
                ) ON CONFLICT DO NOTHING
            """), {
                "cid": client_order_id,
                "sid": row.signal_id,
                "rid": row.decision_id,
                "sv": row.strategy_version,
                "sym": self.symbol,
                "tf": "15m",
                "side": row.signal_type,
                "st": reason,
                "now": datetime.now(timezone.utc)
            })
'''
with open('services/api/live_paper_runtime.py', 'w') as f:
    f.write(content)
