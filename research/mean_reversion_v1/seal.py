"""Immutable-input seal construction and verification."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from research.mean_reversion_v1.data import get_file_hash, validate_artifacts
from research.mean_reversion_v1.manifest import (
    PROTOCOL_VERSION,
    canonical_json,
    get_cost_model_hash,
    get_source_tree_hash,
    get_strategy_definitions_hash,
    hash_object,
)


@dataclass(frozen=True)
class ResearchPaths:
    root: Path
    artifacts: Path

    @classmethod
    def default(cls) -> ResearchPaths:
        root = Path.cwd().resolve()
        return cls(root=root, artifacts=root / ".artifacts" / "research" / "mean_reversion_v1")

    @property
    def config(self) -> Path:
        return self.root / "research" / "mean_reversion_v1" / "config.json"

    @property
    def seal(self) -> Path:
        return self.artifacts / "seal.json"

    @property
    def marker(self) -> Path:
        return self.artifacts / "HOLDOUT_OPENED"


def load_config(paths: ResearchPaths) -> dict[str, object]:
    value = json.loads(paths.config.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Research config must be a JSON object")
    return value


def _assert_base_commit(paths: ResearchPaths, base_git_sha: str) -> None:
    subprocess.run(
        ["git", "cat-file", "-e", f"{base_git_sha}^{{commit}}"],
        cwd=paths.root,
        check=True,
        capture_output=True,
        text=True,
    )


def current_manifest_state(paths: ResearchPaths) -> dict[str, object]:
    config = load_config(paths)
    if str(config.get("protocol_version")) != PROTOCOL_VERSION:
        raise ValueError("Config protocol version does not match implementation")
    base_git_sha = str(config.get("base_git_sha"))
    _assert_base_commit(paths, base_git_sha)
    artifacts = validate_artifacts(paths.artifacts, config)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "base_git_sha": base_git_sha,
        "source_tree_hash": get_source_tree_hash(paths.root),
        "config_hash": get_file_hash(paths.config),
        "primary_dataset_hash": artifacts["primary_dataset_hash"],
        "fred_hash": artifacts["fred_hash"],
        "crosscheck_hashes": {"alpaca": artifacts["alpaca_crosscheck_hash"]},
        "substitution_dataset_hashes": {"yahoo": artifacts["substitution_yahoo_hash"]},
        "strategy_definitions_hash": get_strategy_definitions_hash(),
        "cost_model_hash": get_cost_model_hash(),
        "lock_hash": get_file_hash(paths.root / "uv.lock"),
    }


def create_seal(paths: ResearchPaths) -> dict[str, object]:
    if paths.marker.exists():
        raise RuntimeError("HOLDOUT_ALREADY_BURNED")
    manifest = {
        **current_manifest_state(paths),
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    seal_data: dict[str, object] = {
        "protocol_seal_hash": hash_object(manifest),
        "manifest": manifest,
    }
    paths.artifacts.mkdir(parents=True, exist_ok=True)
    paths.seal.write_text(json.dumps(seal_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return seal_data


def verify_seal(paths: ResearchPaths) -> dict[str, object]:
    if not paths.seal.is_file():
        raise FileNotFoundError("HOLDOUT_REQUIRES_VALID_SEAL")
    seal_data = json.loads(paths.seal.read_text(encoding="utf-8"))
    if not isinstance(seal_data, dict) or not isinstance(seal_data.get("manifest"), dict):
        raise ValueError("Malformed seal")
    manifest = seal_data["manifest"]
    expected_hash = hash_object(manifest)
    if seal_data.get("protocol_seal_hash") != expected_hash:
        raise ValueError("HOLDOUT_INVALIDATED: seal hash is corrupt")
    current = current_manifest_state(paths)
    sealed_state = {key: value for key, value in manifest.items() if key != "created_at"}
    if canonical_json(current) != canonical_json(sealed_state):
        raise ValueError(
            "HOLDOUT_INVALIDATED: sealed source, config, data, or dependencies changed"
        )
    return seal_data
