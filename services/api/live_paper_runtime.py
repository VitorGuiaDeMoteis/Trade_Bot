import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from packages.contracts.broker import BrokerOrder, ExternalBroker

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
        # 1. DB check (already running if we are here)
        account = await self.broker.get_account()
        clock = await self.broker.get_clock()
        positions = await self.broker.get_positions()
        remote_orders = await self.broker.get_orders()

        # 6. broker_orders locais
        with self.engine.begin() as conn:
            local_orders = conn.execute(
                text("SELECT client_order_id FROM broker_orders")
            ).fetchall()
            local_ids = {row.client_order_id for row in local_orders}

        # 7-11. Compare and update
        now = datetime.now(UTC)
        for r_order in remote_orders:
            if r_order.client_order_id in local_ids:
                with self.engine.begin() as conn:
                    conn.execute(
                        text("""
                        UPDATE broker_orders SET
                        broker_order_id = :bid,
                        status = :st,
                        filled_qty = :fq,
                        filled_avg_price = :fap,
                        last_reconciliation_at = :now
                        WHERE client_order_id = :cid
                    """),
                        {
                            "cid": r_order.client_order_id,
                            "bid": r_order.broker_order_id,
                            "st": r_order.status,
                            "fq": r_order.filled_qty,
                            "fap": r_order.filled_avg_price,
                            "now": now,
                        },
                    )

                    if r_order.filled_qty > 0:
                        fill_id = f"{r_order.broker_order_id}-{r_order.filled_qty}"
                        conn.execute(
                            text("""
                            INSERT INTO broker_fills (fill_id, client_order_id, qty, price, filled_at)
                            VALUES (:fid, :cid, :qty, :price, :filled_at)
                            ON CONFLICT DO NOTHING
                        """),
                            {
                                "fid": fill_id,
                                "cid": r_order.client_order_id,
                                "qty": r_order.filled_qty,
                                "price": r_order.filled_avg_price,
                                "filled_at": now,
                            },
                        )

    async def _process_pending(self):
        if not self.execution_ready:
            return

        now = datetime.now(UTC)

        clock = await self.broker.get_clock()
        if not clock.get("is_open", False):
            return

        with self.engine.begin() as conn:
            ctrl = conn.execute(
                text("SELECT armed, activation_cutoff FROM live_paper_control WHERE control_id = 1")
            ).fetchone()

        if not ctrl or not ctrl.armed:
            return

        cutoff = ctrl.activation_cutoff

        with self.engine.begin() as conn:
            latest_candle = conn.execute(
                text(
                    "SELECT close_time FROM candles WHERE symbol = :sym AND timeframe = '1m' ORDER BY close_time DESC LIMIT 1"
                ),
                {"sym": self.symbol},
            ).fetchone()

        if latest_candle:
            # If the market data is more than 5 minutes old while market is open, it's stale.
            if now - latest_candle.close_time > timedelta(minutes=5):
                logger.warning(f"Market data stale for {self.symbol}. Halting execution.")
                return

        query = text("""
            SELECT r.decision_id, r.signal_id, r.decision, r.reason, r.decided_at,
                   s.signal_type, s.strategy_version, s.generated_at, c.close as reference_price
            FROM risk_decisions r
            JOIN signals s ON r.signal_id = s.signal_id
            JOIN candles c ON s.candle_id = c.candle_id
            LEFT JOIN broker_orders b ON r.decision_id = b.risk_decision_id
            WHERE b.client_order_id IS NULL 
              AND r.decision = 'APPROVED'
              AND s.signal_type != 'HOLD'
              AND c.symbol = :symbol
              AND c.timeframe = '15m'
              AND s.strategy_version = 'v2-15m-baseline'
        """)

        with self.engine.begin() as conn:
            rows = conn.execute(query, {"symbol": self.symbol}).fetchall()

        if not rows:
            return

        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        open_orders = await self.broker.get_orders()

        # Open order conflict protection
        for o in open_orders:
            if o.symbol == self.symbol and o.status in (
                "new",
                "accepted",
                "pending_new",
                "partially_filled",
            ):
                logger.warning(
                    f"Conflicting open order exists for {self.symbol}. Halting execution."
                )
                return

        current_qty = 0
        for p in positions:
            if p.symbol == self.symbol:
                current_qty = p.quantity
                break

        # Limit one eligible decision per cycle to avoid multiple buys
        row = rows[0]

        # Cutoff check
        if row.generated_at < cutoff:
            self._persist_failed_order(
                row, f"agy-{row.decision_id}-{row.signal_id}", "rejected_historical"
            )
            return

        # Expiry check (signal valid for 30 minutes max)
        if (now - row.generated_at) > timedelta(minutes=30):
            self._persist_failed_order(
                row, f"agy-{row.decision_id}-{row.signal_id}", "rejected_expired"
            )
            return

        client_order_id = f"agy-{row.decision_id}-{row.signal_id}"

        remote_order = await self.broker.get_order_by_client_order_id(client_order_id)
        if remote_order:
            self._persist_order(row, remote_order)
            return

        # Position sizing
        qty = 0
        if row.signal_type == "BUY":
            if current_qty > 0:
                self._persist_failed_order(row, client_order_id, "rejected_position_exists")
                return
            max_cash = min(account.equity * Decimal("0.10"), account.cash)
            ref_price = Decimal(row.reference_price)
            if ref_price > 0:
                qty = int(max_cash // ref_price)
        elif row.signal_type == "SELL":
            if current_qty <= 0:
                self._persist_failed_order(row, client_order_id, "rejected_no_position")
                return
            qty = current_qty

        if qty <= 0:
            self._persist_failed_order(row, client_order_id, "rejected_sizing")
            return

        try:
            order = await self.broker.submit_order(
                symbol=self.symbol,
                side=row.signal_type,
                quantity=qty,
                client_order_id=client_order_id,
            )
            self._persist_order(row, order)
        except Exception as e:
            logger.error(f"Order failed {client_order_id}: {e}")

    def _persist_order(self, row, order: BrokerOrder):
        with self.engine.begin() as t_conn:
            t_conn.execute(
                text("""
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
            """),
                {
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
                    "now": datetime.now(UTC),
                },
            )

    def _persist_failed_order(self, row, client_order_id: str, reason: str):
        with self.engine.begin() as t_conn:
            t_conn.execute(
                text("""
                INSERT INTO broker_orders (
                    client_order_id, broker_order_id, signal_id, risk_decision_id,
                    strategy_version, symbol, timeframe, side, requested_qty,
                    status, filled_qty, filled_avg_price, submitted_at, last_reconciliation_at
                ) VALUES (
                    :cid, NULL, :sid, :rid, :sv, :sym, :tf, :side, 0, :st, 0, 0, :now, :now
                ) ON CONFLICT DO NOTHING
            """),
                {
                    "cid": client_order_id,
                    "sid": row.signal_id,
                    "rid": row.decision_id,
                    "sv": row.strategy_version,
                    "sym": self.symbol,
                    "tf": "15m",
                    "side": row.signal_type,
                    "st": reason,
                    "now": datetime.now(UTC),
                },
            )
