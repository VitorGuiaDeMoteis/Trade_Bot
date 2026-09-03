import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import AsyncIterator
from uuid import NAMESPACE_URL, uuid5, UUID

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from packages.contracts.provider import MarketDataProvider
from packages.domain.market import Candle, Regime

logger = logging.getLogger("trading_bot.market_data.alpaca")

class AlpacaMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        stream_id: UUID,
        feed: str = "iex",
        symbols: list[str] = ["SPY"],
        timeframe: str = "1h"
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.stream_id = stream_id
        self.feed = feed
        self.symbols = symbols
        self.timeframe = timeframe
        self.state = "offline"
        self.last_event_at = None
        self.sequence_counter = 0

    def _generate_candle_id(self, symbol: str, open_time: datetime) -> tuple[UUID, UUID]:
        candle_id = uuid5(self.stream_id, f"{symbol}-{open_time.isoformat()}")
        return self.stream_id, candle_id

    async def get_historical_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        """Fetch historical bars via REST API."""
        url = "https://data.alpaca.markets/v2/stocks/bars"
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "accept": "application/json"
        }
        # Assuming 1h timeframe for now
        end_dt = datetime.now(UTC)
        start_dt = end_dt - timedelta(days=limit / 8 + 5) # Rough estimation for 1h bars
        
        params = {
            "symbols": self.symbols[0],
            "timeframe": "1Hour",
            "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": limit,
            "feed": self.feed
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
        candles = []
        symbol = self.symbols[0]
        bars = data.get("bars", {}).get(symbol, [])
        for bar in bars:
            open_time = datetime.strptime(bar["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            stream_id, candle_id = self._generate_candle_id(symbol, open_time)
            
            symbol_idx = self.symbols.index(symbol) if symbol in self.symbols else 0
            det_sequence = int(open_time.timestamp()) * 100 + symbol_idx
            
            c = Candle(
                candle_id=candle_id,
                stream_id=stream_id,
                sequence=det_sequence,
                symbol=symbol,
                timeframe=self.timeframe,
                provider="alpaca",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=Decimal(str(bar["o"])),
                high=Decimal(str(bar["h"])),
                low=Decimal(str(bar["l"])),
                close=Decimal(str(bar["c"])),
                volume=int(bar["v"]),
                regime="sideways" # Placeholder
            )
            candles.append(c)
        return candles

    async def subscribe(self) -> AsyncIterator[Candle]:
        """Subscribe to real-time bars via WebSocket."""
        uri = f"wss://stream.data.alpaca.markets/v2/{self.feed}"
        while True:
            try:
                self.state = "connecting"
                async with websockets.connect(uri) as ws:
                    # 1. Wait for connected
                    msg = await ws.recv()
                    logger.info(f"Alpaca WS connected: {msg}")
                    
                    # 2. Auth
                    auth = {"action": "auth", "key": self.api_key, "secret": self.secret_key}
                    await ws.send(json.dumps(auth))
                    msg = await ws.recv()
                    logger.info(f"Alpaca WS auth: {msg}")
                    
                    # 3. Subscribe
                    sub = {"action": "subscribe", "bars": [self.symbols[0]]}
                    await ws.send(json.dumps(sub))
                    msg = await ws.recv()
                    logger.info(f"Alpaca WS subscribe: {msg}")
                    
                    self.state = "connected"
                    
                    # 4. Listen
                    while True:
                        msg = await ws.recv()
                        events = json.loads(msg)
                        self.last_event_at = datetime.now(UTC)
                        
                        for event in events:
                            if event.get("T") == "b":
                                symbol = event["S"]
                                open_time = datetime.strptime(event["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                                stream_id, candle_id = self._generate_candle_id(symbol, open_time)
                                
                                symbol_idx = self.symbols.index(symbol) if symbol in self.symbols else 0
                                det_sequence = int(open_time.timestamp()) * 100 + symbol_idx
                                
                                c = Candle(
                                    candle_id=candle_id,
                                    stream_id=stream_id,
                                    sequence=det_sequence,
                                    symbol=symbol,
                                    timeframe=self.timeframe,
                                    provider="alpaca",
                                    open_time=open_time,
                                    close_time=open_time + timedelta(hours=1),
                                    open=Decimal(str(event["o"])),
                                    high=Decimal(str(event["h"])),
                                    low=Decimal(str(event["l"])),
                                    close=Decimal(str(event["c"])),
                                    volume=int(event["v"]),
                                    regime="sideways"
                                )
                                yield c
            except (ConnectionClosed, OSError, Exception) as e:
                self.state = "offline"
                logger.warning(f"Alpaca WS disconnected: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def get_status(self) -> dict:
        return {
            "provider": "alpaca",
            "feed": self.feed,
            "state": self.state,
            "symbols": self.symbols,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None
        }
