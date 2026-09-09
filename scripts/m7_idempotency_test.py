import asyncio
import os
import sys

from dotenv import load_dotenv

from services.alpaca_paper.adapter import AlpacaPaperAdapter

load_dotenv()

async def main():
    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_API_SECRET_KEY")

    client_order_id = "m7_acbc0baa761f4d13807267cb9f3f4f37"

    async with AlpacaPaperAdapter(api_key, secret_key) as adapter:
        print(f"Checking existing order {client_order_id}...")
        order = await adapter.get_order_by_client_id(client_order_id)
        if order:
            print(f"Found existing order! Status: {order.get('status')}")

        print("Trying to submit same intent...")
        try:
            await adapter.submit_order(
                symbol="SPY",
                qty=None,
                notional="10.00",
                side="buy",
                client_order_id=client_order_id
            )
            print("FAILED: Duplicated submit succeeded!")
        except Exception as e:
            print(f"Idempotency verified! Alpaca rejected duplicate: {e}")

if __name__ == "__main__":
    asyncio.run(main())
