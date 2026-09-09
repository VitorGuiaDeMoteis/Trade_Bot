import logging
from typing import Any

import httpx

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"

class AlpacaPaperError(Exception):
    def __init__(self, message: str, code: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

class AlpacaPaperAdapter:
    """
    Adapter estrito para Alpaca Paper Trading.
    Nenhuma URL LIVE é definida ou permitida.
    """

    def __init__(
        self, api_key: str, secret_key: str, client: httpx.AsyncClient | None = None
    ) -> None:
        if not api_key.strip() or not secret_key.strip():
            raise AlpacaPaperError("Credentials missing", "missing_credentials")
        self._api_key = api_key
        self._secret_key = secret_key
        self._client = client
        self._own_client = False

    async def __aenter__(self) -> "AlpacaPaperAdapter":
        if self._client is None:
            self._own_client = True
            self._client = httpx.AsyncClient(timeout=10.0)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._own_client and self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._client:
            raise RuntimeError("Client not initialized (use async with)")

        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._secret_key,
            }
        )
        url = f"{PAPER_BASE_URL}{path}"

        try:
            response = await self._client.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise AlpacaPaperError("Network error", "network_error", retryable=True) from exc

        if response.status_code == 429:
            raise AlpacaPaperError("Rate limit exceeded", "rate_limit", retryable=True)

        if response.status_code >= 500:
            raise AlpacaPaperError("Server error", "server_error", retryable=True)

        if response.status_code >= 400:
            raise AlpacaPaperError(
                f"Client error {response.status_code}: {response.text}", "client_error", retryable=False
            )

        return response.json()

    async def get_account(self) -> dict[str, Any]:
        return await self._request("GET", "/account")

    async def get_positions(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/positions")

    async def get_open_orders(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/orders", params={"status": "open"})

    async def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET", "/orders:by_client_order_id", params={"client_order_id": client_order_id}
            )
        except AlpacaPaperError as e:
            if e.code == "client_error":
                return None
            raise

    async def submit_order(
        self, symbol: str, qty: int | None, side: str, client_order_id: str, notional: str | None = None
    ) -> dict[str, Any]:
        if side not in ("buy", "sell"):
            raise ValueError("Side must be buy or sell")
        payload = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }
        if qty is not None:
            payload["qty"] = str(qty)
        if notional is not None:
            payload["notional"] = str(notional)
            
        return await self._request("POST", "/orders", json=payload)

    async def cancel_order(self, order_id: str) -> None:
        try:
            await self._request("DELETE", f"/orders/{order_id}")
        except AlpacaPaperError as e:
            if e.code == "client_error":
                return None
            raise

    async def get_fills(self, order_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", "/account/activities/FILL", params={"order_id": order_id})

    async def get_order_by_id(self, order_id: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", f"/orders/{order_id}")
        except AlpacaPaperError as e:
            if e.code == "client_error":
                return None
            raise
