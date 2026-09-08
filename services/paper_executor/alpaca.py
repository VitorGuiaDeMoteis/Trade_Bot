from typing import Any, Literal
from decimal import Decimal
import httpx
import json

from packages.domain.paper import PaperBook, PaperResult
from packages.domain.risk import RiskDecision
from services.paper_executor.broker import ExecutionBroker


class AlpacaPaperExecutor(ExecutionBroker):
    def __init__(self, api_key: str, secret_key: str):
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
        self.base_url = "https://paper-api.alpaca.markets"

    async def get_account(self) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/v2/account", headers=self.headers)
            resp.raise_for_status()
            return dict(resp.json())

    async def get_positions(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/v2/positions", headers=self.headers)
            resp.raise_for_status()
            return list(resp.json())

    async def get_orders(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/v2/orders?status=all", headers=self.headers)
            resp.raise_for_status()
            return list(resp.json())
            
    async def get_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/orders:by_client_order_id",
                headers=self.headers,
                params={"client_order_id": client_order_id}
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return dict(resp.json())

    async def execute(
        self,
        book: PaperBook,
        symbol: str,
        side: Literal["BUY", "SELL"],
        reference: Decimal,
        quantity: int,
        risk: RiskDecision,
    ) -> PaperResult:
        client_order_id = f"agy-{risk.decision_id}-{risk.signal_id}"
        payload = {
            "symbol": symbol,
            "qty": quantity,
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/orders", headers=self.headers, json=payload
            )
            if resp.status_code == 422:
                try:
                    error_data = resp.json()
                    if "order_id" in error_data.get("message", ""):
                        return PaperResult("NO_ACTION", "duplicate_client_order_id")
                except Exception:
                    pass
                return PaperResult("NO_ACTION", "rejected_by_broker")
            resp.raise_for_status()
            resp.json()
            return PaperResult("SUBMITTED", "order_submitted")
