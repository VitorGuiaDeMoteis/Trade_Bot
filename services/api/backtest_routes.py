import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from packages.domain.backtest import digest

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


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

        raw["result_hash"] = claimed
        return raw
    except Exception as e:
        raise ValueError(f"Corrupted report: {e}") from e


def _get_reports_dir(request: Request) -> Path:
    config = request.app.state.configuration
    return Path(config.backtest_artifacts_dir).resolve()


@router.get("")
def list_backtests(request: Request) -> list[dict[str, Any]]:
    reports_dir = _get_reports_dir(request)
    if not reports_dir.exists() or not reports_dir.is_dir():
        return []

    results = []
    for filepath in reports_dir.glob("*.json"):
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
        for filepath in reports_dir.glob("*.json"):
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
def export_backtest(request: Request, result_hash: str) -> FileResponse:
    reports_dir = _get_reports_dir(request)
    if reports_dir.exists() and reports_dir.is_dir():
        for filepath in reports_dir.glob("*.json"):
            if not filepath.is_file():
                continue
            try:
                report = _load_and_validate_report(filepath)
                if report["result_hash"] == result_hash:
                    short_hash = result_hash[:8]
                    return FileResponse(
                        path=filepath,
                        filename=f"trade-bot-backtest-{short_hash}.json",
                        media_type="application/json",
                    )
            except ValueError:
                continue

    raise HTTPException(status_code=404, detail="backtest_not_found")
