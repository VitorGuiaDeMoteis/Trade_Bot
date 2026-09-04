import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from packages.contracts.observer import canonical, checksum, parse_output
from packages.contracts.observer_real import REAL_MODEL, WEIGHTS_HASH
from services.api.models import observer_analysis_runs

router = APIRouter(prefix="/api/v1/observer", tags=["observer"])


class ObserverStatus(BaseModel):
    status: str
    provider: str | None
    model: str | None
    model_version: str | None
    prompt_version: str | None
    as_of_utc: datetime | None
    latency_ms: int | None
    error_code: str | None


class ObserverAnalysisItem(BaseModel):
    analysis_id: UUID
    as_of_utc: datetime | None
    created_at: datetime
    status: str
    regime: str | None
    confidence: float | None
    risk_flags_count: int
    provider: str
    model: str
    model_version: str
    prompt_version: str
    latency_ms: int
    fallback: str | None
    error_code: str | None


class ObserverAnalysisDetail(BaseModel):
    analysis_id: UUID
    as_of_utc: datetime | None
    created_at: datetime
    provider: str
    model: str
    model_version: str
    image_digest: str | None = None
    prompt_version: str
    schema_version: str
    input_hash: str | None
    output_hash: str | None
    latency_ms: int
    status: str
    error_code: str | None
    fallback: str | None
    validated_output: dict[str, Any] | None


def _validated(row: Mapping[str, Any]) -> dict[str, Any]:
    """Persisted data is untrusted at the HTTP boundary; never return raw output."""
    value = dict(row)
    try:
        identity = (value["provider"], value["model"], value["model_version"])
        known = identity == ("fake", "deterministic-observer", "1") or (
            identity[:2] == ("docker", "local-observer")
            and re.fullmatch(r"sha256:[a-f0-9]{64}", identity[2]) is not None
        )
        if identity == ("oci-local", REAL_MODEL, "sha256:" + WEIGHTS_HASH):
            known = (
                re.fullmatch(r"sha256:[a-f0-9]{64}", value.get("image_digest") or "") is not None
            )
        elif value.get("image_digest") is not None:
            raise ValueError("image_digest")
        if (
            not known
            or value["prompt_version"] != "observer-v1"
            or value["schema_version"] != "1.0"
        ):
            raise ValueError("metadata")
        for key in ("input_hash", "output_hash", "prompt_hash"):
            if value[key] is not None and not re.fullmatch(r"[a-f0-9]{64}", value[key]):
                raise ValueError("hash")
        errors = {
            "INVALID_SNAPSHOT",
            "DISABLED",
            "PROVIDER_DEGRADED",
            "NO_CANDLES",
            "STALE_DATA",
            "INVALID_TIMEOUT",
            "TIMEOUT",
            "MODEL_UNAVAILABLE",
            "INVALID_OUTPUT",
            "MODEL_ERROR",
        }
        if value["status"] == "OK":
            if value["error_code"] is not None or value["fallback"] is not None:
                raise ValueError("status")
            output = parse_output(canonical(value["validated_output"])).model_dump(mode="json")
            if checksum(output) != value["output_hash"]:
                raise ValueError("output_hash")
            value["validated_output"] = output
        elif value["status"] == "DEGRADED":
            if (
                value["error_code"] not in errors
                or value["fallback"] != "HOLD"
                or value["validated_output"] is not None
                or value["output_hash"] is not None
            ):
                raise ValueError("status")
        else:
            raise ValueError("status")
        return value
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "observer_audit_invalid") from None


def _read(
    request: Request, analysis_id: UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    query = select(observer_analysis_runs)
    if analysis_id is not None:
        query = query.where(observer_analysis_runs.c.analysis_id == analysis_id)
    query = query.order_by(
        desc(observer_analysis_runs.c.created_at), observer_analysis_runs.c.analysis_id
    ).limit(limit)
    try:
        with request.app.state.database.connect() as conn:
            return [_validated(row) for row in conn.execute(query).mappings()]
    except SQLAlchemyError:
        raise HTTPException(503, "observer_database_unavailable") from None


@router.get("/status", response_model=ObserverStatus)
def get_observer_status(request: Request) -> ObserverStatus:
    rows = _read(request, limit=1)
    row = rows[0] if rows else None

    if not row:
        return ObserverStatus(
            status="DISABLED",
            provider=None,
            model=None,
            model_version=None,
            prompt_version=None,
            as_of_utc=None,
            latency_ms=None,
            error_code=None,
        )

    return ObserverStatus(
        status=row["status"],
        provider=row["provider"],
        model=row["model"],
        model_version=row["model_version"],
        prompt_version=row["prompt_version"],
        as_of_utc=row["as_of_utc"],
        latency_ms=row["latency_ms"],
        error_code=row["error_code"],
    )


@router.get("/analyses", response_model=list[ObserverAnalysisItem])
def list_analyses(request: Request) -> list[ObserverAnalysisItem]:
    rows = _read(request)

    items = []
    for row in rows:
        regime_val = None
        confidence_val = None
        risk_count = 0
        output = row["validated_output"]
        if output:
            regime_dict = output.get("regime", {})
            regime_val = regime_dict.get("label")
            confidence_val = regime_dict.get("confidence")
            risk_count = len(output.get("risk_flags", []))

        items.append(
            ObserverAnalysisItem(
                analysis_id=row["analysis_id"],
                as_of_utc=row["as_of_utc"],
                created_at=row["created_at"],
                status=row["status"],
                regime=regime_val,
                confidence=confidence_val,
                risk_flags_count=risk_count,
                provider=row["provider"],
                model=row["model"],
                model_version=row["model_version"],
                prompt_version=row["prompt_version"],
                latency_ms=row["latency_ms"],
                fallback=row["fallback"],
                error_code=row["error_code"],
            )
        )
    return items


@router.get("/analyses/{analysis_id}", response_model=ObserverAnalysisDetail)
def get_analysis_detail(request: Request, analysis_id: UUID) -> ObserverAnalysisDetail:
    rows = _read(request, analysis_id, limit=1)
    row = rows[0] if rows else None

    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return ObserverAnalysisDetail(
        analysis_id=row["analysis_id"],
        as_of_utc=row["as_of_utc"],
        created_at=row["created_at"],
        provider=row["provider"],
        model=row["model"],
        model_version=row["model_version"],
        image_digest=row["image_digest"],
        prompt_version=row["prompt_version"],
        schema_version=row["schema_version"],
        input_hash=row["input_hash"],
        output_hash=row["output_hash"],
        latency_ms=row["latency_ms"],
        status=row["status"],
        error_code=row["error_code"],
        fallback=row["fallback"],
        validated_output=row["validated_output"],
    )
