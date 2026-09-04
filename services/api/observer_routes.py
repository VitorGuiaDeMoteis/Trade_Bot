from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select

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


class ObserverAnalysisDetail(BaseModel):
    analysis_id: UUID
    as_of_utc: datetime | None
    created_at: datetime
    provider: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    input_hash: str | None
    output_hash: str | None
    latency_ms: int
    status: str
    error_code: str | None
    fallback: str | None
    validated_output: dict[str, Any] | None


@router.get("/status", response_model=ObserverStatus)
def get_observer_status(request: Request) -> ObserverStatus:
    engine = request.app.state.database
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(observer_analysis_runs)
                .order_by(desc(observer_analysis_runs.c.created_at))
                .limit(1)
            )
            .mappings()
            .first()
        )

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
    engine = request.app.state.database
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(observer_analysis_runs)
                .order_by(desc(observer_analysis_runs.c.created_at))
                .limit(50)
            )
            .mappings()
            .all()
        )

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
            )
        )
    return items


@router.get("/analyses/{analysis_id}", response_model=ObserverAnalysisDetail)
def get_analysis_detail(request: Request, analysis_id: UUID) -> ObserverAnalysisDetail:
    engine = request.app.state.database
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(observer_analysis_runs).where(
                    observer_analysis_runs.c.analysis_id == analysis_id
                )
            )
            .mappings()
            .first()
        )

    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return ObserverAnalysisDetail(
        analysis_id=row["analysis_id"],
        as_of_utc=row["as_of_utc"],
        created_at=row["created_at"],
        provider=row["provider"],
        model=row["model"],
        model_version=row["model_version"],
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
