"""Alpaca Market Data only: canonical REST 1Hour; WS minute bars are hints."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from packages.contracts.market import MarketDataStatus, ProviderState
from packages.contracts.provider import MarketDataProvider
from packages.domain.market import Candle
from packages.domain.market_bar import MarketBar
from packages.domain.timeframes import timeframe_duration
from services.market_data.calendar import regular_session
from services.market_data.errors import ProviderError

logger = logging.getLogger("trading_bot.market_data.alpaca")
BACKOFF = (1, 2, 5, 10, 30)


class Socket(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


def alpaca_timeframe(timeframe: str) -> str:
    timeframe_duration(timeframe)
    return {"1h": "1Hour"}[timeframe]


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("utc_required")
    return result.astimezone(UTC)


class AlpacaMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        feed: str,
        symbols: list[str],
        timeframe: str,
        *,
        client: httpx.AsyncClient | None = None,
        socket_factory: Callable[[], Awaitable[Socket]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timer: Callable[[], float] = monotonic,
        poll_seconds: float = 60,
    ) -> None:
        if not api_key.strip() or not secret_key.strip():
            raise ProviderError("missing_alpaca_credentials")
        if feed not in {"iex", "sip"} or not symbols or any(not s for s in symbols):
            raise ProviderError("invalid_feed_or_symbols")
        alpaca_timeframe(timeframe)
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
        self._auth = {"action": "auth", "key": api_key, "secret": secret_key}
        self.feed, self.symbols, self.timeframe = feed, list(dict.fromkeys(symbols)), timeframe
        self.clock, self.sleep, self.timer = clock, sleep, timer
        self.poll_seconds = poll_seconds
        self.client = client or httpx.AsyncClient(timeout=15)
        self._own_client = client is None
        self.socket_factory = socket_factory or self._connect
        self._state: ProviderState = "connecting"
        self._error: str | None = None
        self._last_message: datetime | None = None
        self._last_bar: datetime | None = None
        self._last_open: dict[str, datetime] = {}
        self._socket: Socket | None = None

    async def _connect(self) -> Socket:
        try:
            return await connect(
                f"wss://stream.data.alpaca.markets/v2/{self.feed}",
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=20,
            )
        except InvalidStatus as error:
            status = error.response.status_code
            code = {401: "unauthorized", 403: "feed_forbidden"}.get(
                status, "websocket_http_rejected"
            )
            raise self._fail(code, retryable=status == 429 or status >= 500) from None
        except InvalidHandshake:
            raise self._fail("websocket_handshake_failed", retryable=True) from None

    def _fail(self, code: str, *, retryable: bool = False) -> ProviderError:
        self._state = "reconnecting" if retryable else "configuration_error"
        self._error = code
        logger.warning(
            json.dumps(
                {
                    "event": "market.provider.status",
                    "reason": code,
                    "provider": "alpaca",
                    "state": self._state,
                    "occurred_at": self.clock().isoformat(),
                    "correlation_id": str(uuid4()),
                }
            )
        )
        return ProviderError(code, retryable=retryable)

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        *,
        start: datetime | None = None,
    ) -> list[MarketBar | Candle]:
        mapped = alpaca_timeframe(timeframe)
        if symbol not in self.symbols or not 1 <= limit <= 10000:
            raise ValueError("invalid_symbol_or_limit")
        if start is not None and start.utcoffset() != timedelta(0):
            raise ValueError("utc_required")
        # End filters OPEN timestamps: full hour plus a late-trade grace.
        end = self.clock() - timeframe_duration(timeframe) - timedelta(seconds=60)
        beginning = start or end - timedelta(days=max(30, limit // 4 + 10))
        if beginning > end:
            return []
        params: dict[str, str | int] = {
            "symbols": symbol,
            "timeframe": mapped,
            "feed": self.feed,
            "adjustment": "raw",
            "sort": "asc" if start else "desc",
            "start": beginning.isoformat(),
            "end": end.isoformat(),
            "limit": limit,
        }
        result: list[MarketBar | Candle] = []
        tokens: set[str] = set()
        while True:
            try:
                response = await self.client.get(
                    "https://data.alpaca.markets/v2/stocks/bars",
                    headers=self._headers,
                    params=params,
                )
            except httpx.RequestError:
                raise self._fail("historical_transport", retryable=True) from None
            if response.status_code in {401, 403}:
                raise self._fail(
                    "unauthorized" if response.status_code == 401 else "feed_forbidden"
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise self._fail("historical_unavailable", retryable=True)
            if response.status_code != 200:
                raise self._fail("historical_request_rejected")
            try:
                payload = json.loads(response.content, parse_float=Decimal)
                grouped = payload["bars"] or {}
                if set(grouped) - {symbol}:
                    raise ValueError("unexpected_symbol")
                for raw in grouped.get(symbol, []):
                    opened = parse_time(raw["t"])
                    if not beginning <= opened <= end:
                        continue
                    volume = Decimal(str(raw["v"]))
                    if volume != volume.to_integral_value():
                        raise ValueError("non_integral_volume")
                    result.append(
                        MarketBar(
                            provider="alpaca",
                            symbol=symbol,
                            timeframe=timeframe,
                            open_time=opened,
                            close_time=opened + timeframe_duration(timeframe),
                            open=Decimal(str(raw["o"])),
                            high=Decimal(str(raw["h"])),
                            low=Decimal(str(raw["l"])),
                            close=Decimal(str(raw["c"])),
                            volume=int(volume),
                            is_closed=True,
                        )
                    )
                token = payload.get("next_page_token")
                if token is not None and not isinstance(token, str):
                    raise ValueError("invalid_page_token")
            except (KeyError, TypeError, ValueError, ArithmeticError):
                error = self._fail("invalid_historical_payload")
                self._state = "degraded"
                raise error from None
            if not token or (start is None and len(result) >= limit):
                break
            if token in tokens:
                raise self._fail("repeated_page_token")
            tokens.add(token)
            params["page_token"] = token
        result.sort(key=lambda bar: bar.open_time)
        if start is None:
            result = result[-limit:]
        if result:
            self._last_bar = max(b.close_time for b in result)
        return result

    async def _receive(self, socket: Socket, timeout: float = 10) -> list[dict[str, Any]]:
        raw = await asyncio.wait_for(socket.recv(), timeout)
        try:
            messages = json.loads(raw, parse_float=Decimal)
            if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
                raise ValueError("invalid_envelope")
        except (TypeError, ValueError):
            raise self._fail("invalid_ws_payload") from None
        self._last_message = self.clock()
        for message in messages:
            if message.get("T") == "error":
                code = message.get("code")
                names = {
                    400: "invalid_symbol_or_request",
                    401: "unauthorized",
                    402: "auth_failed",
                    403: "already_authenticated",
                    404: "auth_timeout",
                    405: "symbol_limit",
                    406: "connection_limit",
                    407: "slow_client",
                    409: "feed_forbidden",
                    410: "invalid_subscription",
                    500: "provider_internal",
                }
                raise self._fail(names.get(code, "provider_rejected"), retryable=code in {407, 500})
        return messages

    async def handshake(self, socket: Socket) -> None:
        welcome = await self._receive(socket)
        if not any(m.get("T") == "success" and m.get("msg") == "connected" for m in welcome):
            raise self._fail("connection_ack_missing")
        await socket.send(json.dumps(self._auth))
        auth = await self._receive(socket)
        if not any(m.get("T") == "success" and m.get("msg") == "authenticated" for m in auth):
            raise self._fail("authentication_ack_missing")
        await socket.send(
            json.dumps(
                {
                    "action": "subscribe",
                    "bars": self.symbols,
                    "updatedBars": self.symbols,
                }
            )
        )
        subscription = await self._receive(socket)
        if not any(
            m.get("T") == "subscription"
            and set(self.symbols) <= set(m.get("bars", []))
            and set(self.symbols) <= set(m.get("updatedBars", []))
            for m in subscription
        ):
            raise self._fail("subscription_ack_missing")
        self._state, self._error = "connected", None

    def resume_from(self, symbol: str, opened: datetime) -> None:
        self._last_open[symbol] = opened

    async def refresh(self) -> AsyncIterator[MarketBar | Candle]:
        for symbol in self.symbols:
            for bar in await self.get_historical_candles(
                symbol,
                self.timeframe,
                start=self._last_open.get(symbol),
            ):
                yield bar
                self._last_open[symbol] = max(
                    self._last_open.get(symbol, bar.open_time), bar.open_time
                )

    async def subscribe(self) -> AsyncIterator[MarketBar | Candle]:
        attempt = 0
        while True:
            established: float | None = None
            try:
                self._state = "connecting" if attempt == 0 else "reconnecting"
                self._socket = await self.socket_factory()
                await self.handshake(self._socket)
                established = self.timer()
                due = self.timer()
                while True:
                    if self.timer() >= due:
                        async for bar in self.refresh():
                            yield bar
                        due = self.timer() + self.poll_seconds
                    try:
                        messages = await self._receive(self._socket, max(0.01, due - self.timer()))
                    except TimeoutError:
                        continue
                    for message in messages:
                        if message.get("T") in {"b", "u"}:
                            if message.get("S") not in self.symbols:
                                raise self._fail("unexpected_ws_symbol")
                            # Minute data is a liveness hint only. The bounded REST
                            # refresh obtains canonical, closed hourly bars.
                            parse_time(message["t"])
                    if self.timer() - established >= 60:
                        attempt = 0
            except ProviderError as error:
                if not error.retryable:
                    raise
            except (ConnectionClosed, OSError, TimeoutError):
                self._fail("stream_disconnected", retryable=True)
            except (ValueError, KeyError, TypeError):
                raise self._fail("invalid_ws_payload") from None
            finally:
                if self._socket is not None:
                    await self._socket.close()
                    self._socket = None
            if established is not None and self.timer() - established >= 60:
                attempt = 0
            await self.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            attempt += 1

    def get_status(self) -> MarketDataStatus:
        state, now = self._state, self.clock()
        session = regular_session(now)
        if state == "connected":
            if session is None or not session[0] <= now < session[1]:
                state = "market_closed"
            elif now > session[0] + timedelta(hours=2) and (
                self._last_bar is None or now - self._last_bar > timedelta(hours=2)
            ):
                state = "delayed"
        return MarketDataStatus(
            provider="alpaca",
            feed=self.feed,
            state=state,
            symbols=self.symbols,
            timeframe=self.timeframe,
            session="regular",
            last_message_at=self._last_message,
            last_bar_at=self._last_bar,
            error=self._error,
        )

    async def close(self) -> None:
        if self._socket is not None:
            await self._socket.close()
        if self._own_client:
            await self.client.aclose()
        self._state = "stopped"
