from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from packages.contracts.broker import (
    BrokerAccount,
    BrokerClock,
    BrokerOrder,
    BrokerPosition,
    ExternalBroker,
)


class AlpacaPaperBroker(ExternalBroker):
    def __init__(self, api_key: str, secret_key: str):
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
        self.base_url = "https://paper-api.alpaca.markets"

    @staticmethod
    def _parse_time(t_str: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        except (AttributeError, ValueError, TypeError) as exc:
            raise ValueError("invalid_broker_timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("invalid_broker_timestamp")
        return parsed.astimezone(UTC)

    @staticmethod
    def _whole_quantity(value: Any) -> int:
        quantity = Decimal(str(value))
        if not quantity.is_finite() or quantity != quantity.to_integral_value():
            raise ValueError("invalid_broker_quantity")
        return int(quantity)

    def _map_order(self, data: dict[str, Any]) -> BrokerOrder:
        return BrokerOrder(
            client_order_id=str(data["client_order_id"]),
            broker_order_id=str(data["id"]),
            symbol=str(data["symbol"]).upper(),
            side=str(data["side"]).upper(),
            status=str(data["status"]),
            requested_qty=self._whole_quantity(data["qty"]),
            filled_qty=self._whole_quantity(data["filled_qty"]),
            filled_avg_price=Decimal(data.get("filled_avg_price") or "0"),
            submitted_at=self._parse_time(data["submitted_at"]),
            updated_at=self._parse_time(data["updated_at"]),
        )

    async def get_account(self) -> BrokerAccount:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(f"{self.base_url}/v2/account", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return BrokerAccount(
                currency=data.get("currency", "USD"),
                cash=Decimal(data.get("cash", "0")),
                equity=Decimal(data.get("equity", "0")),
                buying_power=Decimal(data.get("buying_power", "0")),
            )

    async def get_positions(self) -> list[BrokerPosition]:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(f"{self.base_url}/v2/positions", headers=self.headers)
            resp.raise_for_status()
            return [
                BrokerPosition(
                    symbol=p["symbol"],
                    quantity=self._whole_quantity(p["qty"]),
                    average_entry_price=Decimal(p["avg_entry_price"]),
                    current_price=Decimal(p["current_price"]),
                )
                for p in resp.json()
            ]

    async def get_orders(self) -> list[BrokerOrder]:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(
                f"{self.base_url}/v2/orders", headers=self.headers, params={"status": "all"}
            )
            resp.raise_for_status()
            return [self._map_order(o) for o in resp.json()]

    async def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder | None:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(
                f"{self.base_url}/v2/orders:by_client_order_id",
                headers=self.headers,
                params={"client_order_id": client_order_id},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._map_order(resp.json())

    async def get_clock(self) -> BrokerClock:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(f"{self.base_url}/v2/clock", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return BrokerClock(
                is_open=data.get("is_open", False),
                timestamp=self._parse_time(data["timestamp"]),
            )

    async def submit_order(
        self, symbol: str, side: str, quantity: int, client_order_id: str
    ) -> BrokerOrder:
        payload = {
            "symbol": symbol,
            "qty": quantity,
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/v2/orders", headers=self.headers, json=payload
            )
            resp.raise_for_status()
            order = self._map_order(resp.json())
            if (
                order.client_order_id != client_order_id
                or order.symbol != symbol.upper()
                or order.side != side.upper()
                or order.requested_qty != quantity
            ):
                raise ValueError("broker_order_identity_mismatch")
            return order
