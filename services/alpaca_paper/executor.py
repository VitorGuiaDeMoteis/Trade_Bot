import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection

from packages.domain.paper import PaperResult
from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.models import paper_orders

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
            # Update DB with remote_order status
            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(
                    broker_order_id=remote_order.get("id"),
                    broker_status=remote_order.get("status"),
                    status=self._map_status(remote_order.get("status"))
                )
            )
        else:
            # Prova de ausência da ordem original -> podemos reenviar
            connection.execute(
                paper_orders.update()
                .where(paper_orders.c.order_id == order_id)
                .values(status="CANCELED", reason="timeout_not_found_on_broker")
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
        
        # 1. Persistir intent: SUBMITTING
        client_order_id = f"m7_{order_id.hex}"
        
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
                reason="intent_persisted",
                client_order_id=client_order_id
            )
        )
        
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
        status = self._map_status(alpaca_order.get("status"))
        broker_order_id = alpaca_order.get("id")
        
        connection.execute(
            paper_orders.update()
            .where(paper_orders.c.order_id == order_id)
            .values(
                broker_order_id=broker_order_id,
                broker_status=alpaca_order.get("status"),
                status=status
            )
        )
        
        return PaperResult(status, "submitted_to_broker", quantity)
