#!/usr/bin/env python3
"""Create a reviewed, backed-up Alpaca Paper V1 database baseline."""

# ruff: noqa: E402 -- direct execution needs the project root on sys.path first.

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import func, insert, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.paper_ops import database_revision, runtime_pid, runtime_settings
from services.alpaca_paper.adapter import AlpacaPaperAdapter
from services.api.config import Settings
from services.api.database import (
    acquire_paper_runtime_lock,
    create_database_engine,
    paper_runtime_lock_available,
    release_paper_runtime_lock,
)
from services.api.models import (
    broker_fills,
    broker_orders,
    broker_portfolio_snapshots,
    broker_positions,
    paper_events,
    paper_fills,
    paper_marks,
    paper_orders,
    paper_outcomes,
    paper_runs,
    portfolio_snapshots,
    positions,
    risk_decisions,
    signals,
    system_controls,
)

BACKUP_DIR = PROJECT_ROOT / ".artifacts" / "paper-baseline-backups"

# Children precede parents. alembic_version, candles, system_events,
# observer audit, and market archives are deliberately excluded.
RESET_TABLES = (
    broker_fills,
    broker_orders,
    paper_outcomes,
    paper_fills,
    paper_orders,
    broker_positions,
    broker_portfolio_snapshots,
    positions,
    portfolio_snapshots,
    paper_marks,
    paper_events,
    system_controls,
    risk_decisions,
    signals,
    paper_runs,
)


def planned_backup_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return BACKUP_DIR / f"trading_bot_dev-before-paper-reset-{stamp}.dump"


def api_is_active() -> bool:
    try:
        return httpx.get("http://127.0.0.1:8000/health", timeout=0.75).status_code in (200, 503)
    except Exception:
        return False


async def broker_state(
    settings: Settings,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    assert settings.alpaca_api_key_id and settings.alpaca_api_secret_key
    adapter = AlpacaPaperAdapter(
        settings.alpaca_api_key_id.get_secret_value(),
        settings.alpaca_api_secret_key.get_secret_value(),
    )
    async with adapter:
        account = await adapter.get_account()
        positions_state = await adapter.get_positions()
        open_orders = await adapter.get_open_orders()
    return account, positions_state, open_orders


def inspect_plan(engine, settings, backup_path: Path) -> dict[str, object]:  # type: ignore[no-untyped-def]
    current, head = database_revision(engine)
    with engine.connect() as connection:
        counts = {
            table.name: connection.scalar(select(func.count()).select_from(table))
            for table in RESET_TABLES
        }
        control = connection.execute(select(system_controls)).mappings().first()
    account, broker_positions_state, broker_orders_state = asyncio.run(broker_state(settings))
    return {
        "mode": "DRY_RUN",
        "target_database": settings.postgres_db,
        "environment": settings.app_env,
        "database_role": settings.database_role,
        "schema_current": current,
        "schema_head": head,
        "schema_at_head": current == [head],
        "runtime_pid": runtime_pid(),
        "runtime_api_active": api_is_active(),
        "runtime_lock_available": paper_runtime_lock_available(engine),
        "runtime_paused": None if control is None else control["paused"],
        "tables": counts,
        "broker_account": account.get("status"),
        "broker_positions": [
            {
                "symbol": row.get("symbol"),
                "qty": row.get("qty"),
                "market_value": row.get("market_value"),
            }
            for row in broker_positions_state
        ],
        "broker_open_orders": [
            {
                "id": row.get("id"),
                "client_order_id": row.get("client_order_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "status": row.get("status"),
            }
            for row in broker_orders_state
        ],
        "backup_file": str(backup_path),
    }


def create_backup(settings, backup_path: Path) -> None:  # type: ignore[no-untyped-def]
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PGPASSWORD"] = settings.postgres_password.get_secret_value()
    partial_path = backup_path.with_suffix(".dump.partial")
    partial_path.unlink(missing_ok=True)
    if shutil.which("pg_dump"):
        command = [
            "pg_dump",
            "--host",
            settings.postgres_host,
            "--port",
            str(settings.postgres_port),
            "--username",
            settings.postgres_user,
            "--dbname",
            settings.postgres_db,
            "--format=custom",
            "--file",
            str(partial_path),
        ]
        completed = subprocess.run(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "--username",
            settings.postgres_user,
            "--dbname",
            settings.postgres_db,
            "--format=custom",
        ]
        with partial_path.open("wb") as output:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
    if completed.returncode != 0 or not partial_path.is_file() or partial_path.stat().st_size == 0:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError("operational_backup_failed")
    partial_path.replace(backup_path)


def create_clean_baseline(engine, account) -> str:  # type: ignore[no-untyped-def]
    initial_cash = Decimal(str(account.get("cash", "0")))
    if not initial_cash.is_finite() or initial_cash <= 0:
        raise RuntimeError("invalid_broker_cash_for_baseline")
    run_id = uuid4()
    now = datetime.now(UTC)
    dataset_hash = hashlib.sha256(b"[]").hexdigest()

    with engine.begin() as connection:
        for table in RESET_TABLES:
            connection.execute(table.delete())
        connection.execute(
            insert(paper_runs).values(
                run_id=run_id,
                mode="ALPACA_PAPER",
                provider="alpaca",
                status="READY",
                initial_cash=initial_cash,
                cash=initial_cash,
                fees=Decimal("0"),
                realized_pnl=Decimal("0"),
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
                dataset=[],
                dataset_hash=dataset_hash,
                step=0,
                as_of=None,
                created_at=now,
            )
        )
        connection.execute(
            insert(system_controls).values(
                control_id=1,
                active_run_id=run_id,
                paused=True,
                updated_at=now,
            )
        )
    return str(run_id)


def validate_confirm_preconditions(plan: dict[str, object]) -> None:
    if plan["runtime_pid"] is not None or plan["runtime_api_active"] is True:
        raise RuntimeError("runtime_is_active")
    if plan["runtime_paused"] is not True:
        raise RuntimeError("runtime_is_not_paused")
    if plan["runtime_lock_available"] is not True:
        raise RuntimeError("runtime_is_active")
    if plan["broker_positions"]:
        raise RuntimeError("broker_has_open_positions")
    if plan["broker_open_orders"]:
        raise RuntimeError("broker_has_open_orders")


def perform_confirm(settings, engine, plan, backup_path: Path) -> str:  # type: ignore[no-untyped-def]
    validate_confirm_preconditions(plan)
    create_backup(settings, backup_path)

    # Re-read broker state after backup and immediately before mutation.
    account, current_positions, current_orders = asyncio.run(broker_state(settings))
    if current_positions:
        raise RuntimeError("broker_positions_changed_after_backup")
    if current_orders:
        raise RuntimeError("broker_orders_changed_after_backup")
    return create_clean_baseline(engine, account)


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe Alpaca Paper baseline reset")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", metavar="TOKEN")
    args = parser.parse_args()

    if args.confirm and args.confirm != "RESET_PAPER_BASELINE":
        parser.error("--confirm requires the exact token RESET_PAPER_BASELINE")

    try:
        settings = runtime_settings()
        engine = create_database_engine(settings)
        backup_path = planned_backup_path()
        try:
            plan = inspect_plan(engine, settings, backup_path)
            print(json.dumps(plan, indent=2, ensure_ascii=False, default=str))
            if args.dry_run:
                return
            if plan["schema_at_head"] is not True:
                raise RuntimeError("schema_not_at_alembic_head")

            # Refresh liveness immediately before the guarded operation.
            plan["runtime_pid"] = runtime_pid()
            plan["runtime_api_active"] = api_is_active()
            runtime_lock = acquire_paper_runtime_lock(engine)
            try:
                run_id = perform_confirm(settings, engine, plan, backup_path)
            finally:
                release_paper_runtime_lock(runtime_lock)
            print(
                json.dumps(
                    {
                        "result": "CLEAN_BASELINE_CREATED",
                        "backup_file": str(backup_path),
                        "active_run_id": run_id,
                        "paused": True,
                    },
                    indent=2,
                )
            )
        finally:
            engine.dispose()
    except Exception as error:
        parser.exit(1, f"RESET REFUSED: {error}\n")


if __name__ == "__main__":
    main()
