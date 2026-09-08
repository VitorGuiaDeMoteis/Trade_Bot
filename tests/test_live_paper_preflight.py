import pytest
import sqlalchemy as sa

from scripts.live_paper import _preflight_arm
from services.api.config import Settings


@pytest.mark.anyio
async def test_preflight_fails_on_schema_drift(clean_db_for_migrations):
    # This fixture migrates to head usually, but clean_db_for_migrations from migration test doesn't.
    # Let's import run_alembic from test_migration_002bd or just use alembic directly.
    from tests.test_migration_002bd import run_alembic
    run_alembic("head")

    engine = clean_db_for_migrations

    # Verify preflight works initially
    settings = Settings(
        execution_mode="alpaca_paper",
        alpaca_api_key_id="test",
        alpaca_api_secret_key="test",
        market_data_provider="simulator"
    )
    # mock broker to avoid network calls?
    # Actually _preflight_arm calls AlpacaPaperBroker.get_clock()
    # We should mock AlpacaPaperBroker inside _preflight_arm
    from unittest.mock import AsyncMock, patch
    with patch("scripts.live_paper.AlpacaPaperBroker") as MockBroker:
        instance = MockBroker.return_value
        instance.base_url = "https://paper-api.alpaca.markets"
        instance.get_clock = AsyncMock(return_value=None)
        instance.get_account = AsyncMock(return_value=None)

        assert await _preflight_arm(settings, engine)

        # Now remove a physical constraint
        with engine.begin() as conn:
            conn.execute(sa.text("ALTER TABLE broker_orders DROP CONSTRAINT ck_broker_orders_side;"))
        
        # Now preflight should fail because constraint is physically missing
        assert not await _preflight_arm(settings, engine)
