import asyncio
import os
import sys
from datetime import datetime, UTC
from uuid import uuid4

# Setup paths for importing services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.api.config import get_settings
from services.market_data.alpaca_provider import AlpacaMarketDataProvider

async def main():
    settings = get_settings()
    if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
        print("❌ Alpaca credentials not found in environment!")
        print("Please export ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY")
        sys.exit(1)
        
    print(f"✅ Credentials found. Connecting to Alpaca {settings.alpaca_data_feed} feed for {settings.market_symbols}...")
    
    provider = AlpacaMarketDataProvider(
        api_key=settings.alpaca_api_key_id,
        secret_key=settings.alpaca_api_secret_key.get_secret_value(),
        stream_id=uuid4(),
        feed=settings.alpaca_data_feed,
        symbols=[s.strip() for s in settings.market_symbols.split(",")],
        timeframe=settings.market_timeframe
    )
    
    print("\n--- Testing Historical Fetch ---")
    try:
        candles = await provider.get_historical_candles("SPY", "1Hour", limit=5)
        print(f"✅ Fetched {len(candles)} historical candles for SPY.")
        if candles:
            print(f"   Last candle: {candles[-1].close_time} | Close: {candles[-1].close}")
    except Exception as e:
        print(f"❌ Historical fetch failed: {e}")
        
    print("\n--- Testing WebSocket Subscription ---")
    print("⏳ Waiting for 2 real-time candles... (Press Ctrl+C to abort if market is closed)")
    
    try:
        count = 0
        async for candle in provider.subscribe():
            print(f"🟢 [WS] {candle.symbol} | {candle.close_time} | Open: {candle.open} | Close: {candle.close}")
            count += 1
            if count >= 2:
                print("✅ Real-time data stream works!")
                break
    except asyncio.CancelledError:
        print("Cancelled.")
    except Exception as e:
        print(f"❌ WebSocket failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSmoke test interrupted by user.")
