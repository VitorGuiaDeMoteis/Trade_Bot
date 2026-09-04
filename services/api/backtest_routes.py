import json
import re
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from packages.domain.backtest import digest

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


def _validate_display_contract(raw: dict[str, Any]) -> None:
    """Validate fields consumed by Flutter without recomputing any financial value."""
    for key in ("manifest_hash", "dataset_hash"):
        if not re.fullmatch("[0-9a-f]{64}", raw[key]):
            raise ValueError("Invalid report identity")

    def fields(row: Any, decimals: str = "", integers: str = "", strings: str = "") -> None:
        if not isinstance(row, dict):
            raise ValueError("Invalid report record")
        for key in decimals.split():
            if not isinstance(row.get(key), str) or not Decimal(row[key]).is_finite():
                raise ValueError("Invalid decimal string")
        for key in integers.split():
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError("Invalid report count")
        for key in strings.split():
            if not isinstance(row.get(key), str):
                raise ValueError("Invalid report label")
            if key in {"timestamp", "opened_at", "closed_at", "executed_at"}:
                if datetime.fromisoformat(row[key]).utcoffset() is None:
                    raise ValueError("Missing report timezone")

    fields(raw["config"], "initial_cash fee_bps slippage_bps")
    fields(
        raw["metrics"],
        "initial_cash final_equity return_pct max_drawdown max_drawdown_pct "
        "total_pnl_net fees slippage",
        "closed_trades winning_trades losing_trades open_positions",
    )
    for key in ("win_rate_pct", "average_profit", "average_loss", "profit_factor"):
        if key not in raw["metrics"]:
            raise ValueError("Missing nullable metric")
        if raw["metrics"][key] is not None:
            fields(raw["metrics"], key)
    for row in raw["equity_curve"]:
        fields(row, "equity cash market_value drawdown", "step", "timestamp")
    for row in raw["trades"]:
        fields(row, "fees net_pnl", "quantity", "symbol opened_at closed_at")
    for row in raw["outcomes"]:
        fields(row, "reference_price", "quantity", "symbol status reason executed_at")


def _load_and_validate_report(filepath: Path) -> dict[str, Any]:
    try:
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid format")

        claimed = raw.pop("result_hash", None)
        if not claimed:
            raise ValueError("Missing result_hash")

        if digest(raw) != claimed:
            raise ValueError("Hash mismatch")

        if raw.get("mode") != "BACKTEST" or raw.get("schema_version") != "1.0":
            raise ValueError("Unsupported or invalid report")

        for key in (
            "manifest_hash",
            "dataset_hash",
            "engine_version",
            "strategy_version",
            "risk_version",
        ):
            if not isinstance(raw.get(key), str):
                raise ValueError("Missing report metadata")
        for key in ("config", "metrics"):
            if not isinstance(raw.get(key), dict):
                raise ValueError("Missing report section")
        for key in ("equity_curve", "trades", "outcomes", "positions", "signals"):
            if not isinstance(raw.get(key), list):
                raise ValueError("Missing report records")
        _validate_display_contract(raw)
        raw["result_hash"] = claimed
        return raw
    except Exception as e:
        raise ValueError(f"Corrupted report: {e}") from e


def _get_reports_dir(request: Request) -> Path:
    config = request.app.state.configuration
    return Path(config.backtest_artifacts_dir).resolve()


def _report_paths(reports_dir: Path) -> Iterator[Path]:
    if not reports_dir.is_dir():
        return
    for filepath in sorted(reports_dir.glob("*.json")):
        try:
            if filepath.is_symlink() or filepath.resolve().parent != reports_dir:
                continue
            if filepath.is_file():
                yield filepath
        except OSError:
            continue


@router.get("")
def list_backtests(request: Request) -> list[dict[str, Any]]:
    reports_dir = _get_reports_dir(request)
    if not reports_dir.exists() or not reports_dir.is_dir():
        return []

    results = []
    for filepath in _report_paths(reports_dir):
        if not filepath.is_file():
            continue
        try:
            report = _load_and_validate_report(filepath)
            summary = {
                "result_hash": report["result_hash"],
                "manifest_hash": report["manifest_hash"],
                "dataset_hash": report["dataset_hash"],
                "engine_version": report["engine_version"],
                "strategy_version": report["strategy_version"],
                "risk_version": report["risk_version"],
                "config": report["config"],
                "metrics": report["metrics"],
            }
            results.append(summary)
        except ValueError:
            # Corrupted report, fail closed (ignore in list)
            pass

    return results


@router.get("/{result_hash}")
def get_backtest(request: Request, result_hash: str) -> dict[str, Any]:
    # Path traversal protection is implicit since we do not use
    # result_hash to build the filename directly.
    reports_dir = _get_reports_dir(request)
    if reports_dir.exists() and reports_dir.is_dir():
        for filepath in _report_paths(reports_dir):
            if not filepath.is_file():
                continue
            try:
                report = _load_and_validate_report(filepath)
                if report["result_hash"] == result_hash:
                    return report
            except ValueError:
                continue

    raise HTTPException(status_code=404, detail="backtest_not_found")


@router.get("/{result_hash}/export")
def export_backtest(request: Request, result_hash: str) -> JSONResponse:
    reports_dir = _get_reports_dir(request)
    if reports_dir.exists() and reports_dir.is_dir():
        for filepath in _report_paths(reports_dir):
            if not filepath.is_file():
                continue
            try:
                report = _load_and_validate_report(filepath)
                if report["result_hash"] == result_hash:
                    short_hash = result_hash[:8]
                    # Return the validated in-memory snapshot, never reopen a mutable file.
                    return JSONResponse(
                        content=report,
                        headers={
                            "Content-Disposition": (
                                f'attachment; filename="trade-bot-backtest-{short_hash}.json"'
                            )
                        },
                    )
            except ValueError:
                continue

    raise HTTPException(status_code=404, detail="backtest_not_found")
