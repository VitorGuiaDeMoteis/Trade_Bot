import logging
from datetime import datetime, UTC
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, select

from packages.domain.paper import PaperResult
from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.models import paper_orders, broker_orders

logger = logging.getLogger("trading_bot.alpaca_paper")

class AlpacaPaperExecutor:
    """Fronteira separada do PaperExecutor local."""
    def __init__(self, adapter: AlpacaPaperAdapter) -> None:
        self.adapter = adapter

    async def _handle_timeout_or_disconnect(
        self, connection: Connection, order_id: UUID, client_order_id: str
    ) -> None:
        """
        Idempotência: Se houver timeout, nunca reenviar cegamente.
        Pesquisar por client_order_id.
        """
        remote_order = await self.adapter.get_order_by_client_id(client_order_id)
        if remote_order:
            # Reconciliar estado
            broker_status = remote_order.get("status")
            status = self._map_status(broker_status)
            
            connection.execute(
                broker_orders.update()
                .where(broker_orders.c.order_id == order_id)
                .values(
                    broker_order_id=remote_order.get("id"),
                    status=broker_status,
                    filled_quantity=Decimal(remote_order.get("filled_qty", "0")),
                    last_reconciled_at=datetime.now(UTC)
                )
            )
            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(status=status)
            )
        else:
            # Prova de ausência da ordem original -> podemos reenviar
            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(status="CANCELED", reason="timeout_not_found_on_broker")
            )
            connection.execute(
                broker_orders.update()
                .where(broker_orders.c.order_id == order_id)
                .values(status="CANCELED", last_reconciled_at=datetime.now(UTC))
            )

    def _map_status(self, alpaca_status: str | None) -> str:
        if not alpaca_status:
            return "UNKNOWN"
        mapping = {
            "new": "NEW",
            "accepted": "ACCEPTED",
            "pending_new": "PENDING_NEW",
            "partially_filled": "PARTIALLY_FILLED",
            "filled": "FILLED",
            "pending_cancel": "PENDING_CANCEL",
            "canceled": "CANCELED",
            "rejected": "REJECTED",
            "expired": "EXPIRED",
            "replaced": "REPLACED",
        }
        return mapping.get(alpaca_status.lower(), "UNKNOWN")

    async def submit(
        self,
        connection: Connection,
        run_id: UUID,
        signal_id: UUID,
        risk: RiskDecision,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: int,
        order_id: UUID,
        requested_at: datetime
    ) -> PaperResult:
        
        client_order_id = f"m7_{order_id.hex}"
        
        # 1. Persistir intent: SUBMITTING
        try:
            with connection.begin_nested():
                connection.execute(
                    paper_orders.insert().values(
                        order_id=order_id,
                        run_id=run_id,
                        signal_id=signal_id,
                        risk_decision_id=risk.decision_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        filled_quantity=0,
                        status="SUBMITTING",
                        requested_at=requested_at,
                        idempotency_key=order_id,
                        reason="intent_persisted"
                    )
                )
                
                connection.execute(
                    broker_orders.insert().values(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        status="submitting",
                        requested_notional=None,
                        requested_quantity=Decimal(quantity),
                        filled_quantity=Decimal("0"),
                        last_reconciled_at=datetime.now(UTC)
                    )
                )
        except Exception as e:
            if "IntegrityError" in type(e).__name__ or "UniqueViolation" in type(e).__name__:
                logger.error(f"IntegrityError: {e}")
                logger.warning(f"Duplicate intent locally blocked for order {order_id}")
                return PaperResult("UNKNOWN", "duplicate_intent", quantity)
            raise
        
        # 2. Chamar Alpaca
        try:
            alpaca_order = await self.adapter.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side.lower(),
                client_order_id=client_order_id
            )
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            await self._handle_timeout_or_disconnect(connection, order_id, client_order_id)
            return PaperResult("REJECTED", "network_error", quantity)
            
        # 3. Atualizar status
        broker_status = alpaca_order.get("status")
        status = self._map_status(broker_status)
        broker_order_id = alpaca_order.get("id")
        
        connection.execute(
            broker_orders.update()
            .where(broker_orders.c.order_id == order_id)
            .values(
                broker_order_id=broker_order_id,
                status=broker_status,
                last_reconciled_at=datetime.now(UTC)
            )
        )
        
        connection.execute(
            paper_orders.update()
            .where(paper_orders.c.order_id == order_id)
            .values(status=status)
        )
        
        return PaperResult(status, "submitted_to_broker", quantity)

    async def reconcile_order(self, connection: Connection, order_id: UUID) -> None:
        from services.api.models import broker_fills
        
        row = connection.execute(
            select(broker_orders.c.broker_order_id, broker_orders.c.client_order_id)
            .where(broker_orders.c.order_id == order_id)
        ).first()
        
        if not row:
            return
            
        broker_order_id = row.broker_order_id
        client_order_id = row.client_order_id
        
        if broker_order_id:
            remote_order = await self.adapter.get_order_by_id(broker_order_id)
        else:
            remote_order = await self.adapter.get_order_by_client_id(client_order_id)
            
        if not remote_order:
            connection.execute(
                paper_orders.update().where(paper_orders.c.order_id == order_id)
                .values(status="CANCELED", reason="not_found_on_broker")
            )
            connection.execute(
                broker_orders.update().where(broker_orders.c.order_id == order_id)
                .values(status="canceled", last_reconciled_at=datetime.now(UTC))
            )
            return

        new_status = remote_order.get("status")
        filled_qty = Decimal(remote_order.get("filled_qty", "0"))
        actual_broker_id = remote_order.get("id")
        
        connection.execute(
            broker_orders.update().where(broker_orders.c.order_id == order_id)
            .values(
                broker_order_id=actual_broker_id,
                status=new_status,
                filled_quantity=filled_qty,
                last_reconciled_at=datetime.now(UTC)
            )
        )
        
        mapped_status = self._map_status(new_status)
        connection.execute(
            paper_orders.update().where(paper_orders.c.order_id == order_id)
            .values(status=mapped_status, filled_quantity=int(filled_qty))
        )
        
        if new_status in ("partially_filled", "filled") and actual_broker_id:
            activities = await self.adapter.get_fills(actual_broker_id)
            for act in activities:
                fill_id = act.get("id")
                qty = Decimal(act.get("qty", "0"))
                price = Decimal(act.get("price", "0"))
                
                try:
                    with connection.begin_nested():
                        connection.execute(
                            broker_fills.insert().values(
                                broker_fill_id=fill_id,
                                order_id=order_id,
                                quantity=qty,
                                price=price,
                                fee=Decimal("0"),
                                filled_at=datetime.now(UTC)
                            )
                        )
                except Exception as e:
                    if "IntegrityError" in type(e).__name__ or "UniqueViolation" in type(e).__name__:
                        pass
                    else:
                        raise
