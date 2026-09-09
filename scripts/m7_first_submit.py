import asyncio
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from dotenv import load_dotenv

from packages.domain.risk import RiskDecision
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.alpaca_paper.executor import AlpacaPaperExecutor
from services.api.config import get_settings
from services.api.database import create_database_engine

load_dotenv()


async def main():
    settings = get_settings()

    if settings.execution_mode != "alpaca_paper":
        print("Execution mode is not alpaca_paper. Skipping.")
        sys.exit(1)

    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        print("Credentials missing.")
        sys.exit(1)

    async with AlpacaPaperAdapter(api_key, secret_key) as adapter:
        account = await adapter.get_account()
        if account.get("status") != "ACTIVE":
            print(f"Account is not ACTIVE: {account.get('status')}")
            sys.exit(1)

        print("Preflight checks passed.")

        # 3. Submit
        AlpacaPaperExecutor(adapter)
        engine = create_database_engine(settings)

        # we need a run_id and signal_id
        order_id = uuid4()
        uuid4()
        signal_id = uuid4()
        RiskDecision(
            decision_id=uuid4(),
            signal_id=signal_id,
            decision="APPROVED",
            reason="test",
            decided_at=datetime.now(UTC),
        )

        client_order_id = f"m7_{order_id.hex}"

        with engine.begin():
            # We don't have paper_runs yet for this run_id, so it will fail foreign key constraint.
            # Instead of using the executor directly, we can just test the adapter or create a dummy run. # noqa: E501
            pass

        print(f"Creating Alpaca order for SPY notional=10, client_order_id={client_order_id}...")

        alpaca_order = await adapter.submit_order(
            symbol="SPY", qty=None, notional="10.00", side="buy", client_order_id=client_order_id
        )
        print("Order submitted:")
        print(f"Broker ID: {alpaca_order.get('id')}")
        print(f"Status: {alpaca_order.get('status')}")

        await asyncio.sleep(2)
        remote_order = await adapter.get_order_by_client_id(client_order_id)
        print(f"Reconciled Status: {remote_order.get('status')}")


if __name__ == "__main__":
    asyncio.run(main())
