"""Frozen JSON artifacts and atomic report publication; no provider or paper-store access."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from packages.contracts.market import CandleResponse
from packages.domain.backtest import ENGINE_VERSION, Dataset, digest, encode, manifest
from packages.domain.market import Candle
from packages.domain.paper import PaperConfig


def load_manifest(path: Path) -> tuple[Dataset, PaperConfig]:
    def no_float(value: str) -> None:
        raise ValueError("backtest_decimal_strings_required")

    raw = json.loads(
        path.read_text(encoding="utf-8"), parse_float=no_float, parse_constant=no_float
    )
    if not isinstance(raw, dict):
        raise ValueError("backtest_invalid_manifest")
    try:
        claimed = raw.pop("manifest_hash")
        if claimed != digest(raw):
            raise ValueError("backtest_manifest_hash_mismatch")
        if (
            raw["engine_version"] != ENGINE_VERSION
            or raw["mode"] != "BACKTEST"
            or raw["schema_version"] != "1.0"
        ):
            raise ValueError("backtest_unsupported_manifest")
        from decimal import Decimal

        config = PaperConfig(**{k: Decimal(v) for k, v in raw["config"].items()})
        dataset = Dataset(
            tuple(Candle(**CandleResponse.model_validate(c).model_dump()) for c in raw["candles"])
        )
        if (
            raw["dataset_hash"] != dataset.hash
            or manifest(dataset, config)["manifest_hash"] != claimed
        ):
            raise ValueError("backtest_dataset_hash_mismatch")
        return dataset, config
    except (KeyError, TypeError) as error:
        raise ValueError("backtest_invalid_manifest") from error


def write_artifact(path: Path, payload: dict[str, Any]) -> None:
    """Replace the requested artifact only after full serialization and fsync."""
    content = encode(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".backtest-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
