"""Canonical protocol definitions and hashing helpers."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

PROTOCOL_VERSION = "1.3"

STRATEGY_DEFINITIONS: dict[str, dict[str, object]] = {
    "B0": {"kind": "cash", "rebalance": "monthly"},
    "B1": {"kind": "equal_weight", "rebalance": "monthly"},
    "B2": {"kind": "fixed_weight", "weights": {"SPY": 0.6, "TLT": 0.4}, "rebalance": "monthly"},
    "AM_PRIMARY": {
        "kind": "am",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "rebalance": "monthly",
    },
    "A1": {
        "kind": "am",
        "lookback_months": 6,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "rebalance": "monthly",
    },
    "A2": {
        "kind": "am",
        "lookback_months": 12,
        "skip_months": 1,
        "absolute_filter": "tbill",
        "rebalance": "monthly",
    },
    "A3": {
        "kind": "am",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "zero",
        "rebalance": "monthly",
    },
    "A4": {
        "kind": "am",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "rebalance": "quarterly",
    },
    "RAM_PRIMARY": {
        "kind": "ram",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "k": 3,
        "rebalance": "monthly",
    },
    "R1": {
        "kind": "ram",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "k": 2,
        "rebalance": "monthly",
    },
    "R2": {
        "kind": "ram",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "k": 4,
        "rebalance": "monthly",
    },
    "R3": {
        "kind": "ram",
        "lookback_months": 6,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "k": 3,
        "rebalance": "monthly",
    },
    "R4": {
        "kind": "ram",
        "lookback_months": 12,
        "skip_months": 1,
        "absolute_filter": "tbill",
        "k": 3,
        "rebalance": "monthly",
    },
    "R5": {
        "kind": "ram",
        "lookback_months": 12,
        "skip_months": 0,
        "absolute_filter": "tbill",
        "k": 3,
        "rebalance": "quarterly",
    },
}

COST_MODEL: dict[str, object] = {
    "quoted_units": "basis_points_round_trip",
    "round_trip_bps": [5.0, 10.0, 15.0],
    "per_side_rate_formula": "round_trip_bps / 2 / 10000",
    "application": "absolute_traded_notional_at_next_session_open",
}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def hash_object(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def get_strategy_definitions_hash(definitions: Mapping[str, object] | None = None) -> str:
    return hash_object(dict(definitions) if definitions is not None else STRATEGY_DEFINITIONS)


def get_cost_model_hash(model: Mapping[str, object] | None = None) -> str:
    return hash_object(dict(model) if model is not None else COST_MODEL)


def hash_files(paths: Sequence[Path], *, root: Path) -> str:
    """Hash normalized relative path, byte length, and real file content."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def sealed_source_paths(root: Path) -> list[Path]:
    package = root / "research" / "mean_reversion_v1"
    paths = [path for path in package.rglob("*.py") if "__pycache__" not in path.parts]
    paths.extend([package / "config.json", root / "IMPLEMENT.md"])
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing sealed source inputs: {missing}")
    return paths


def get_source_tree_hash(root: Path) -> str:
    return hash_files(sealed_source_paths(root), root=root)


def get_git_info(root: Path) -> dict[str, str]:
    def run_cmd(cmd):
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        return res.stdout.strip()

    head = run_cmd(["git", "rev-parse", "HEAD"])
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status = run_cmd(["git", "status", "--porcelain"])

    return {
        "git_head": head,
        "git_branch": branch,
        "git_worktree_path": str(root.resolve()),
        "git_is_clean": "YES" if not status else "NO",
    }


def create_run_manifest(
    root: Path, config: dict, data_hashes: dict, command: str, period: dict
) -> dict:
    git_info = get_git_info(root)
    if git_info["git_is_clean"] == "NO":
        raise RuntimeError("DIRTY_RESEARCH_TREE")

    return {
        "protocol_version": PROTOCOL_VERSION,
        **git_info,
        "source_tree_hash": get_source_tree_hash(root),
        "config_hash": hash_object(config),
        "strategy_hash": get_strategy_definitions_hash(),
        "cost_model_hash": get_cost_model_hash(),
        "dependency_lock_hash": hash_files([root / "uv.lock"], root=root)
        if (root / "uv.lock").exists()
        else "NO_LOCK",
        "command": command,
        "run_started_at": dt.datetime.now(dt.UTC).isoformat(),
        "requested_period": period,
        "dataset_hashes": data_hashes,
        "status": "RUNNING",
    }


def finalize_run_manifest(
    manifest: dict, artifact_hashes: dict, status: str = "COMPLETED_VALID"
) -> dict:
    manifest["run_finished_at"] = dt.datetime.now(dt.UTC).isoformat()
    manifest["status"] = status
    manifest["artifact_hashes"] = artifact_hashes
    manifest["run_manifest_hash"] = hash_object(manifest)
    return manifest
