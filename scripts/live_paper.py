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

    try:
        import sqlalchemy as sa
        inspector = sa.inspect(engine)
        tables = inspector.get_table_names()

        if "broker_orders" not in tables:
            print("ERROR: Missing table broker_orders")
            return False
        if "broker_fills" not in tables:
            print("ERROR: Missing table broker_fills")
            return False
        if "live_paper_control" not in tables:
            print("ERROR: Missing table live_paper_control")
            return False

        bo_pk = inspector.get_pk_constraint("broker_orders")
        if not bo_pk or "client_order_id" not in bo_pk.get("constrained_columns", []):
            print("ERROR: broker_orders PK must be client_order_id")
            return False

        bo_uqs = [uq.get("name") for uq in inspector.get_unique_constraints("broker_orders")]
        if "uq_broker_order_risk_decision" not in bo_uqs:
            print("ERROR: Missing unique constraint uq_broker_order_risk_decision on broker_orders")
            return False

        bo_cols = {col["name"]: str(col["type"]) for col in inspector.get_columns("broker_orders")}
        if not bo_cols.get("requested_qty", "").startswith("BIGINT"):
            print("ERROR: broker_orders.requested_qty must be BIGINT")
            return False
        if not bo_cols.get("filled_qty", "").startswith("BIGINT"):
            print("ERROR: broker_orders.filled_qty must be BIGINT")
            return False

        bo_cks = [ck.get("name") for ck in inspector.get_check_constraints("broker_orders")]
        required_bo_cks = [
            "ck_broker_orders_side",
            "ck_broker_orders_timeframe",
            "ck_broker_orders_status",
            "ck_broker_orders_quantities",
            "ck_broker_orders_fill_price",
            "ck_broker_orders_filled_complete",
        ]
        for ck in required_bo_cks:
            if ck not in bo_cks:
                print(f"ERROR: Missing check constraint {ck} on broker_orders")
                return False

        bf_fks = inspector.get_foreign_keys("broker_fills")
        if not any("client_order_id" in fk.get("constrained_columns", []) and fk.get("referred_table") == "broker_orders" for fk in bf_fks):
            print("ERROR: broker_fills missing FK to broker_orders.client_order_id")
            return False

        bf_cols = {col["name"]: str(col["type"]) for col in inspector.get_columns("broker_fills")}
        if not bf_cols.get("qty", "").startswith("BIGINT"):
            print("ERROR: broker_fills.qty must be BIGINT")
            return False

        bf_cks = [ck.get("name") for ck in inspector.get_check_constraints("broker_fills")]
        if "ck_broker_fills_values" not in bf_cks:
            print("ERROR: Missing check constraint ck_broker_fills_values on broker_fills")
            return False

        lpc_cols = {col["name"]: str(col["type"]) for col in inspector.get_columns("live_paper_control")}
        if not lpc_cols.get("control_id", "").startswith("BIGINT"):
            print("ERROR: live_paper_control.control_id must be BIGINT")
            return False

        lpc_cks = [ck.get("name") for ck in inspector.get_check_constraints("live_paper_control")]
        if "ck_live_paper_singleton" not in lpc_cks:
            print("ERROR: Missing check constraint ck_live_paper_singleton on live_paper_control")
            return False

        candles_cks = [ck.get("name") for ck in inspector.get_check_constraints("candles")]
        if "ck_candles_timeframe_duration" not in candles_cks:
            print("ERROR: Missing check constraint ck_candles_timeframe_duration on candles")
            return False

    except Exception as e:
        print(f"ERROR: Schema physical validation failed: {e}")
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
