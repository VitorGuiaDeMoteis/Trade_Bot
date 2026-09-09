import asyncio
import os
import sys

from dotenv import load_dotenv

from services.alpaca_paper.adapter import AlpacaPaperAdapter

load_dotenv()


async def main():
    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        print("Preflight SKIPPED: ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY is missing.")
        sys.exit(0)

    async with AlpacaPaperAdapter(api_key, secret_key) as adapter:
        print("Executing READ-ONLY preflight against Alpaca Paper...")
        try:
            account = await adapter.get_account()
            print(f"Account ID: {account.get('id')} - Status: {account.get('status')}")
            eq = account.get("equity")
            bp = account.get("buying_power")
            print(f"Paper Equity: {eq} - Buying Power: {bp}")

            positions = await adapter.get_positions()
            print(f"Active Positions: {len(positions)}")
            for p in positions:
                print(f"  - {p.get('symbol')}: {p.get('qty')} @ {p.get('avg_entry_price')}")

            orders = await adapter.get_open_orders()
            print(f"Open Orders: {len(orders)}")
            for o in orders:
                print(f"  - {o.get('symbol')} {o.get('side')} {o.get('qty')} ({o.get('status')})")

        except Exception as e:
            print(f"Preflight FAILED: {e}")
            sys.exit(1)

    print("Preflight PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
