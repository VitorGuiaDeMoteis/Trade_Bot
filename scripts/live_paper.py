import argparse
import asyncio
import sys
from datetime import UTC, datetime

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import text

from services.api.config import Settings
from services.api.database import create_database_engine
from services.paper_executor.alpaca import AlpacaPaperBroker


async def _preflight_arm(settings: Settings, engine) -> bool:
    if settings.execution_mode != "alpaca_paper":
        print(f"ERROR: EXECUTION_MODE must be alpaca_paper, got {settings.execution_mode}")
        return False

    if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
        print("ERROR: Missing ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY")
        return False

    broker = AlpacaPaperBroker(
        settings.alpaca_api_key_id.get_secret_value(),
        settings.alpaca_api_secret_key.get_secret_value(),
    )
    if broker.base_url != "https://paper-api.alpaca.markets":
        print(f"ERROR: Provider endpoint is not paper: {broker.base_url}")
        return False

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: check_database failed: {e}")
        return False

    try:
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()
            if current_rev != head_rev:
                print(
                    f"ERROR: Database schema out of date. Current: {current_rev}, Head: {head_rev}"
                )
                return False
    except Exception as e:
        print(f"ERROR: Alembic revision check failed: {e}")
        return False

    try:
        await broker.get_clock()
    except Exception as e:
        print(f"ERROR: Alpaca get_clock failed: {e}")
        return False

    try:
        await broker.get_account()
    except Exception as e:
        print(f"ERROR: Alpaca get_account failed: {e}")
        return False

    return True


async def main():
    parser = argparse.ArgumentParser(description="Live Paper CLI")
    parser.add_argument("action", choices=["status", "arm", "disarm"])
    args = parser.parse_args()

    load_dotenv()
    settings = Settings()
    engine = create_database_engine(settings)

    if args.action == "status":
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT armed, armed_at, activation_cutoff "
                    "FROM live_paper_control WHERE control_id = 1"
                )
            ).fetchone()

        if row:
            print(f"Status: {'ARMED' if row.armed else 'DISARMED'}")
            if row.armed:
                print(f"Armed At: {row.armed_at}")
                print(f"Activation Cutoff: {row.activation_cutoff}")
        else:
            print("Status: UNINITIALIZED (DISARMED)")

    elif args.action == "arm":
        ok = await _preflight_arm(settings, engine)
        if not ok:
            print("ARM PREFLIGHT FAILED. Aborting.")
            sys.exit(1)

        with engine.begin() as conn:
            now = datetime.now(UTC)
            conn.execute(
                text("""
                INSERT INTO live_paper_control (
                    control_id, armed, armed_at, updated_at, activation_cutoff
                )
                VALUES (1, true, :now, :now, :now)
                ON CONFLICT (control_id) DO UPDATE SET 
                    armed = true,
                    armed_at = EXCLUDED.armed_at,
                    updated_at = EXCLUDED.updated_at,
                    activation_cutoff = EXCLUDED.activation_cutoff
                """),
                {"now": now},
            )
        print("ARMED. Alpaca Paper execution enabled.")

    elif args.action == "disarm":
        with engine.begin() as conn:
            now = datetime.now(UTC)
            conn.execute(
                text("""
                INSERT INTO live_paper_control (control_id, armed, updated_at)
                VALUES (1, false, :now)
                ON CONFLICT (control_id) DO UPDATE SET 
                    armed = false,
                    updated_at = EXCLUDED.updated_at
                """),
                {"now": now},
            )
        print("DISARMED. All executions paused.")


if __name__ == "__main__":
    asyncio.run(main())
