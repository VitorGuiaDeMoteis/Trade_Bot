import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, replace
from dotenv import load_dotenv

from services.market_data.alpaca_provider import AlpacaMarketDataProvider
from packages.domain.backtest import Dataset, manifest, encode
from packages.domain.paper import PaperConfig

load_dotenv()

async def main():
    api_key = os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        print("Missing Alpaca credentials")
        sys.exit(1)

    symbols = ["SPY", "AAPL", "TSLA"]
    provider = AlpacaMarketDataProvider(
        api_key=api_key,
        secret_key=secret_key,
        feed="iex",
        symbols=symbols,
        timeframe="1h",
    )
    
    start_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    
    print("Downloading historical data...")
    all_candles = []
    for sym in symbols:
        print(f"Fetching {sym}...")
        candles = await provider.get_historical_candles(sym, "1h", limit=2000, start=start_time)
        fixed_candles = [replace(c, is_closed=True, timeframe="1h") for c in candles]
        all_candles.extend(fixed_candles)
        print(f"Got {len(candles)} for {sym}")
    
    if not all_candles:
        print("No candles fetched.")
        return

    dataset = Dataset(tuple(all_candles))
    config = PaperConfig()
    
    m = manifest(dataset, config)
    raw = encode(m)
    
    out = "services/replay/data/large-history.json"
    with open(out, "w") as f:
        f.write(raw)
    print(f"Dataset saved to {out} with {len(dataset.candles)} candles.")

if __name__ == "__main__":
    asyncio.run(main())
