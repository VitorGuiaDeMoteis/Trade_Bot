"""Operational controls for the Alpaca Paper V1 runtime.

All commands are fail-closed and use the explicit runtime database identity.
No command in this module can select the Alpaca LIVE endpoint.
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select, text, update

from services.alpaca_paper.adapter import PAPER_BASE_URL, AlpacaPaperAdapter
from services.alpaca_paper.worker import ACTIVE_ORDER_STATUSES, AlpacaPaperWorker
from services.api.config import Settings, validate_database_target
from services.api.database import (
    check_database,
    create_database_engine,
    get_alembic_head,
    get_alembic_heads,
    paper_runtime_lock_available,
)
from services.api.models import (
    broker_fills,
    broker_orders,
    broker_portfolio_snapshots,
    broker_positions,
    paper_orders,
    paper_runs,
    system_controls,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PID_FILE = PROJECT_ROOT / ".runtime" / "alpaca-paper.pid"


def runtime_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def runtime_settings() -> Settings:
    settings = Settings(execution_mode="alpaca_paper")
    validate_database_target(settings)
    if settings.app_env == "test" or settings.database_role != "runtime":
        raise RuntimeError("paper_runtime_requires_runtime_environment")
    if PAPER_BASE_URL != "https://paper-api.alpaca.markets/v2":
        raise RuntimeError("alpaca_live_endpoint_forbidden")
    return settings


def database_revision(engine) -> tuple[list[str], str]:  # type: ignore[no-untyped-def]
    expected = get_alembic_head()
    with engine.connect() as connection:
        current = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
    return current, expected


def set_paused(engine, paused: bool, *, require_active_run: bool = False) -> None:  # type: ignore[no-untyped-def]
    with engine.begin() as connection:
        control = (
            connection.execute(
                select(system_controls).where(system_controls.c.control_id == 1).with_for_update()
            )
            .mappings()
            .first()
        )
        if control is None:
            raise RuntimeError("system_control_missing_run_baseline_reset_first")
        if require_active_run and control["active_run_id"] is None:
            raise RuntimeError("active_alpaca_paper_run_missing_baseline_reset_first")
        if require_active_run:
            mode = connection.scalar(
                select(paper_runs.c.mode).where(paper_runs.c.run_id == control["active_run_id"])
            )
            if mode != "ALPACA_PAPER":
                raise RuntimeError(f"active_run_mode_mismatch:{mode}")
            connection.execute(
                update(paper_runs)
                .where(paper_runs.c.run_id == control["active_run_id"])
                .values(status="RUNNING")
            )
        connection.execute(
            update(system_controls)
            .where(system_controls.c.control_id == 1)
            .values(paused=paused, updated_at=datetime.now(UTC))
        )
        confirmed = connection.scalar(
            select(system_controls.c.paused).where(system_controls.c.control_id == 1)
        )
        if confirmed != paused:
            raise RuntimeError("pause_confirmation_failed")


def validate_active_runtime_run(engine) -> None:  # type: ignore[no-untyped-def]
    with engine.connect() as connection:
        control = (
            connection.execute(select(system_controls).where(system_controls.c.control_id == 1))
            .mappings()
            .first()
        )
        if control is None or control["active_run_id"] is None:
            raise RuntimeError("active_alpaca_paper_run_missing_baseline_reset_first")
        mode = connection.scalar(
            select(paper_runs.c.mode).where(paper_runs.c.run_id == control["active_run_id"])
        )
        if mode != "ALPACA_PAPER":
            raise RuntimeError(f"active_run_mode_mismatch:{mode}")


async def run_preflight(release: bool) -> dict[str, Any]:
    settings = runtime_settings()
    heads = get_alembic_heads()
    if len(heads) != 1:
        raise RuntimeError(f"alembic_expected_single_head:{','.join(heads) or 'none'}")

    engine = create_database_engine(settings)
    try:
        if check_database(engine) != "up":
            current, expected = database_revision(engine)
            raise RuntimeError(f"alembic_not_at_head:current={current},head={expected}")
        if not paper_runtime_lock_available(engine):
            raise RuntimeError("alpaca_paper_runtime_already_active")
        validate_active_runtime_run(engine)

        assert settings.alpaca_api_key_id and settings.alpaca_api_secret_key
        adapter = AlpacaPaperAdapter(
            settings.alpaca_api_key_id.get_secret_value(),
            settings.alpaca_api_secret_key.get_secret_value(),
        )
        worker = AlpacaPaperWorker(engine, adapter, settings)
        async with adapter:
            account, positions = await worker.reconcile_once()
            open_orders = await adapter.get_open_orders()

        exposure = sum(
            (Decimal(str(position["market_value"])) for position in positions), Decimal("0")
        )
        if release:
            set_paused(engine, False, require_active_run=True)
        return {
            "app_env": settings.app_env,
            "database": settings.postgres_db,
            "alembic": get_alembic_head(),
            "broker_endpoint": PAPER_BASE_URL,
            "broker_account": account.get("status"),
            "broker_positions": len(positions),
            "broker_open_orders": len(open_orders),
            "broker_exposure": str(exposure),
            "reconciliation": "COMPLETE",
            "execution_released": release,
        }
    finally:
        engine.dispose()


def pause_command() -> dict[str, Any]:
    settings = runtime_settings()
    engine = create_database_engine(settings)
    try:
        set_paused(engine, True)
        return {"database": settings.postgres_db, "paused": True, "confirmed": True}
    finally:
        engine.dispose()


def audit_runtime_fixtures() -> dict[str, Any]:
    settings = runtime_settings()
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            signatures = {
                "replay_runs": connection.scalar(
                    select(func.count())
                    .select_from(paper_runs)
                    .where(paper_runs.c.mode == "REPLAY")
                ),
                "broker_order_b_id": connection.scalar(
                    select(func.count())
                    .select_from(broker_orders)
                    .where(broker_orders.c.broker_order_id == "b_id")
                ),
                "broker_fill_fill_1": connection.scalar(
                    select(func.count())
                    .select_from(broker_fills)
                    .where(broker_fills.c.broker_fill_id == "fill_1")
                ),
            }
        if any(signatures.values()):
            raise RuntimeError(f"runtime_fixture_contamination:{signatures}")
        return {
            "database": settings.postgres_db,
            "runtime_fixture_signatures": signatures,
            "clean": True,
        }
    finally:
        engine.dispose()


def _safe_decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


async def status_command() -> dict[str, Any]:
    settings = runtime_settings()
    engine = create_database_engine(settings)
    result: dict[str, Any] = {
        "app_env": settings.app_env,
        "database": settings.postgres_db,
        "runtime_pid": runtime_pid(),
        "broker_endpoint": PAPER_BASE_URL,
    }
    degraded = False
    local_positions: list[dict[str, Any]] = []
    local_open_orders: int | None = None
    try:
        try:
            result["runtime_lock_available"] = paper_runtime_lock_available(engine)
        except Exception:
            result["runtime_lock_available"] = "UNKNOWN"
            degraded = True
        heads = get_alembic_heads()
        result["alembic_head"] = list(heads)
        try:
            current, expected = database_revision(engine)
            result["alembic_current"] = current
            result["schema_at_head"] = current == [expected] and len(heads) == 1
        except Exception:
            result["alembic_current"] = "UNAVAILABLE"
            result["schema_at_head"] = False
        degraded |= not result["schema_at_head"]

        try:
            with engine.connect() as connection:
                control = connection.execute(select(system_controls)).mappings().first()
                snapshot = (
                    connection.execute(
                        select(broker_portfolio_snapshots).where(
                            broker_portfolio_snapshots.c.provider == "alpaca"
                        )
                    )
                    .mappings()
                    .first()
                )
                local_positions = [
                    dict(row)
                    for row in connection.execute(
                        select(broker_positions).where(broker_positions.c.provider == "alpaca")
                    ).mappings()
                ]
                local_open_orders = connection.scalar(
                    select(func.count())
                    .select_from(paper_orders)
                    .where(paper_orders.c.status.in_(ACTIVE_ORDER_STATUSES))
                )
                active_run_mode = (
                    None
                    if control is None or control["active_run_id"] is None
                    else connection.scalar(
                        select(paper_runs.c.mode).where(
                            paper_runs.c.run_id == control["active_run_id"]
                        )
                    )
                )
            result["runtime_paused"] = None if control is None else control["paused"]
            result["runtime_active_run"] = (
                None if control is None else str(control["active_run_id"] or "") or None
            )
            result["runtime_active_run_mode"] = active_run_mode
            result["local_reconciliation_state"] = (
                "MISSING" if snapshot is None else snapshot["status"]
            )
            result["local_reconciled_at"] = (
                None if snapshot is None else snapshot["last_reconciled_at"].isoformat()
            )
            reconciliation_age = (
                None
                if snapshot is None
                else (datetime.now(UTC) - snapshot["last_reconciled_at"]).total_seconds()
            )
            result["local_reconciliation_age_seconds"] = reconciliation_age
            result["local_runtime_positions"] = [
                {
                    "symbol": row["symbol"],
                    "qty": str(row["quantity"]),
                    "market_value": str(row["market_value"]),
                }
                for row in local_positions
            ]
            result["local_open_orders"] = local_open_orders
            degraded |= snapshot is None or snapshot["status"] != "ACTIVE"
            degraded |= reconciliation_age is None or reconciliation_age > 15
            degraded |= active_run_mode != "ALPACA_PAPER"
        except Exception:
            result["runtime_paused"] = "UNKNOWN"
            result["local_reconciliation_state"] = "UNAVAILABLE"
            degraded = True

        try:
            response = httpx.get("http://127.0.0.1:8000/health", timeout=1.0)
            result["api_health"] = response.json().get("status")
        except Exception:
            result["api_health"] = "OFFLINE"

        try:
            assert settings.alpaca_api_key_id and settings.alpaca_api_secret_key
            adapter = AlpacaPaperAdapter(
                settings.alpaca_api_key_id.get_secret_value(),
                settings.alpaca_api_secret_key.get_secret_value(),
            )
            async with adapter:
                account = await adapter.get_account()
                positions = await adapter.get_positions()
                orders = await adapter.get_open_orders()
            exposure = Decimal("0")
            exposure_known = True
            for position in positions:
                value = _safe_decimal(position.get("market_value"))
                if value is None:
                    exposure_known = False
                else:
                    exposure += value
            for order in orders:
                if str(order.get("side", "")).lower() != "buy":
                    continue
                value = _safe_decimal(order.get("notional"))
                if value is None:
                    exposure_known = False
                else:
                    exposure += value
            result["broker_paper_status"] = account.get("status")
            result["broker_positions"] = [
                {
                    "symbol": p.get("symbol"),
                    "qty": p.get("qty"),
                    "market_value": p.get("market_value"),
                }
                for p in positions
            ]
            result["broker_open_orders"] = len(orders)
            result["broker_exposure"] = str(exposure) if exposure_known else "UNKNOWN"
            broker_position_quantities = {
                str(item.get("symbol")): _safe_decimal(item.get("qty")) for item in positions
            }
            local_position_quantities = {
                str(item["symbol"]): Decimal(str(item["quantity"])) for item in local_positions
            }
            result["broker_local_divergence"] = (
                broker_position_quantities != local_position_quantities
                or local_open_orders is None
                or len(orders) != local_open_orders
            )
            degraded |= account.get("status") != "ACTIVE" or not exposure_known
            degraded |= result["broker_local_divergence"]
        except Exception:
            result["broker_paper_status"] = "UNAVAILABLE"
            result["broker_positions"] = "UNAVAILABLE"
            result["broker_open_orders"] = "UNAVAILABLE"
            result["broker_exposure"] = "UNKNOWN"
            degraded = True

        result["degraded"] = degraded
        return result
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca Paper V1 operational controls")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--release", action="store_true")
    subparsers.add_parser("status")
    subparsers.add_parser("pause")
    subparsers.add_parser("audit-runtime-fixtures")
    args = parser.parse_args()

    try:
        if args.command == "preflight":
            output = asyncio.run(run_preflight(args.release))
        elif args.command == "status":
            output = asyncio.run(status_command())
        elif args.command == "pause":
            output = pause_command()
        else:
            output = audit_runtime_fixtures()
    except Exception as error:
        parser.exit(1, f"FAIL CLOSED: {error}\n")
    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
