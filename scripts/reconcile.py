import asyncio
from services.api.config import Settings
from services.alpaca_paper.worker import AlpacaPaperWorker
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.database import create_database_engine
from sqlalchemy import text

async def rec():
    settings = Settings(execution_mode="alpaca_paper")
    adapter = AlpacaPaperAdapter(
        api_key=settings.alpaca_api_key_id.get_secret_value(),
        secret_key=settings.alpaca_api_secret_key.get_secret_value()
    )
    worker = AlpacaPaperWorker(engine=create_database_engine(settings), adapter=adapter, settings=settings)
    
    async with adapter:
        await worker._snapshot_broker_portfolio()
        await worker._reconcile_active_orders()
    
    with worker.engine.connect() as c:
        pos = c.execute(text("SELECT symbol, quantity FROM broker_positions")).fetchall()
        print("Positions:", pos)
        orders = c.execute(text("SELECT status FROM broker_orders WHERE status NOT IN ('FILLED', 'CANCELED', 'REJECTED')")).fetchall()
        print("Pending orders:", len(orders))

asyncio.run(rec())
