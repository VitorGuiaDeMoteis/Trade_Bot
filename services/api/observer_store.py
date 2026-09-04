"""Trusted audit adapter. Financial tables are neither imported nor written here."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, text

from packages.contracts.observer import AIObserverSnapshot, canonical, checksum, parse_output
from services.api.models import observer_analysis_runs
from services.observer.engine import evaluate
from services.observer.prompt import PROMPT, PROMPT_VERSION
from services.observer.provider import ModelProvider


def analyze(
    engine: Engine,
    analysis_id: UUID,
    snapshot: AIObserverSnapshot | None,
    provider: ModelProvider,
    *,
    enabled: bool = False,
    timeout: float = 2,
) -> dict[str, Any]:
    binding = checksum(
        {
            "input_hash": snapshot.input_hash if snapshot else None,
            "provider": provider.identity.provider,
            "model": provider.identity.model,
            "model_version": provider.identity.model_version,
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": checksum(PROMPT),
            "enabled": enabled,
            "timeout": repr(timeout),
            **({"real_gpu": True} if getattr(provider, "gpu", False) else {}),
            **(
                {"image_digest": provider.identity.image_digest}
                if provider.identity.image_digest
                else {}
            ),
        }
    )
    with engine.begin() as c:
        lock = int.from_bytes(analysis_id.bytes[:8], "big", signed=True)
        c.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        row = (
            c.execute(
                select(observer_analysis_runs).where(
                    observer_analysis_runs.c.analysis_id == analysis_id
                )
            )
            .mappings()
            .first()
        )
        if row:
            stored = dict(row)
            if stored["request_hash"] != binding:
                raise ValueError("observer_analysis_id_conflict")
            if stored["input_hash"] != (snapshot.input_hash if snapshot else None):
                raise ValueError("observer_audit_input_corrupt")
            if stored["sanitized_input"] is not None:
                previous = AIObserverSnapshot.model_validate_json(
                    canonical(stored["sanitized_input"])
                )
                if previous.input_hash != stored["input_hash"]:
                    raise ValueError("observer_audit_input_corrupt")
            if stored["validated_output"] is not None:
                parse_output(canonical(stored["validated_output"]))
                if checksum(stored["validated_output"]) != stored["output_hash"]:
                    raise ValueError("observer_audit_output_corrupt")
            return stored
        result = asyncio.run(evaluate(snapshot, provider, enabled=enabled, timeout=timeout))
        record = {
            "analysis_id": analysis_id,
            "created_at": datetime.now(UTC),
            "request_hash": binding,
            **result,
        }
        c.execute(observer_analysis_runs.insert().values(**record))
        return record
