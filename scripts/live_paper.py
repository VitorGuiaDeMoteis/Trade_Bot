import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy import text

from services.api.config import Settings
from services.api.database import create_database_engine


async def main():
    parser = argparse.ArgumentParser(description="Live Paper CLI")
    parser.add_argument("action", choices=["status", "arm", "disarm"])
    args = parser.parse_args()

    load_dotenv()

    execution_mode = os.getenv("EXECUTION_MODE", "local_paper")
    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")

    engine = create_database_engine(Settings())

    if args.action == "status":
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT armed, armed_at, activation_cutoff FROM live_paper_control WHERE control_id = 1"
                )
            ).fetchone()

        print(f"Execution Mode: {execution_mode}")
        if row:
            print(f"Armed: {row.armed}")
            print(f"Armed At: {row.armed_at}")
            print(f"Activation Cutoff: {row.activation_cutoff}")
        else:
            print("System not initialized in DB.")

    elif args.action == "arm":
        if execution_mode != "alpaca_paper":
            print("ERROR: EXECUTION_MODE must be alpaca_paper")
            sys.exit(1)
        if not api_key or not secret:
            print("ERROR: ALPACA credentials missing")
            sys.exit(1)

        # Optional: Ping broker to confirm
        print("Arming system for Live Paper Trading...")
        now = datetime.now(UTC)

        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO live_paper_control (control_id, armed, armed_at, updated_at, activation_cutoff)
                VALUES (1, true, :now, :now, :now)
                ON CONFLICT (control_id) DO UPDATE SET 
                armed = true,
                armed_at = :now,
                updated_at = :now,
                activation_cutoff = :now
            """),
                {"now": now},
            )

        print("System ARMED successfully!")

    elif args.action == "disarm":
        now = datetime.now(UTC)
        with engine.begin() as conn:
            conn.execute(
                text("""
                UPDATE live_paper_control SET 
                armed = false,
                updated_at = :now
                WHERE control_id = 1
            """),
                {"now": now},
            )
        print("System DISARMED")


if __name__ == "__main__":
    asyncio.run(main())
