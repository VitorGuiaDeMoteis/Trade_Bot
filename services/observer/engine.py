"""Observer failures are audit data, never strategy signals or execution commands."""

import asyncio
import json
from dataclasses import asdict
from datetime import timedelta
from time import monotonic
from typing import Any

from packages.contracts.observer import AIObserverSnapshot, checksum, parse_output
from services.observer.prompt import PROMPT, PROMPT_VERSION
from services.observer.provider import ModelProvider


async def evaluate(
    snapshot: AIObserverSnapshot | None,
    provider: ModelProvider,
    *,
    enabled: bool = False,
    timeout: float = 2,
) -> dict[str, Any]:
    start = monotonic()
    result: dict[str, Any] = {
        **asdict(provider.identity),
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": checksum(PROMPT),
        "schema_version": "1.0",
        "input_hash": snapshot.input_hash if snapshot else None,
        "as_of_utc": snapshot.as_of_utc if snapshot else None,
        "sanitized_input": json.loads(snapshot.payload()) if snapshot else None,
        "output_hash": None,
        "validated_output": None,
        "status": "DEGRADED",
        "fallback": "HOLD",
        "error_code": None,
    }
    error = None
    if snapshot is None:
        error = "INVALID_SNAPSHOT"
    elif not enabled:
        error = "DISABLED"
    elif snapshot.session_state in {"degraded", "delayed", "offline"}:
        error = "PROVIDER_DEGRADED"
    elif not snapshot.candles or any(
        not any(c.symbol == s for c in snapshot.candles) for s in snapshot.symbols
    ):
        error = "NO_CANDLES"
    elif any(
        snapshot.as_of_utc - max(c.close_time for c in snapshot.candles if c.symbol == s)
        > timedelta(hours=2)
        for s in snapshot.symbols
    ):
        error = "STALE_DATA"
    elif not 0 < timeout <= 30:
        error = "INVALID_TIMEOUT"
    else:
        try:
            async with asyncio.timeout(timeout):
                output = await provider.generate(snapshot.payload(), PROMPT)
            parsed = parse_output(output).model_dump(mode="json")
            result.update(
                status="OK", fallback=None, validated_output=parsed, output_hash=checksum(parsed)
            )
        except TimeoutError:
            error = "TIMEOUT"
        except FileNotFoundError:
            error = "MODEL_UNAVAILABLE"
        except (ValueError, UnicodeError, TypeError):
            error = "INVALID_OUTPUT"
        except Exception:
            error = "MODEL_ERROR"
    result["error_code"] = error
    result["latency_ms"] = max(0, int((monotonic() - start) * 1000))
    return result
