from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from research.momentum_v1.bootstrap import block_bootstrap
from research.momentum_v1.cli import app
from research.momentum_v1.data import enforce_date_range, get_file_hash
from research.momentum_v1.holdout import open_holdout
from research.momentum_v1.manifest import (
    COST_MODEL,
    STRATEGY_DEFINITIONS,
    get_cost_model_hash,
    get_source_tree_hash,
    get_strategy_definitions_hash,
)
from research.momentum_v1.run_experiments import assert_public_period
from research.momentum_v1.seal import ResearchPaths, create_seal, verify_seal


def test_package_cli_executes() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Momentum Experiment V1.3" in result.output


def test_no_2026_observations() -> None:
    with pytest.raises(ValueError, match="DATA_RANGE_VIOLATION"):
        enforce_date_range(pd.DataFrame(index=pd.DatetimeIndex(["2026-01-01"])))


def test_dataset_hash_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"research-data")
    assert get_file_hash(path) == get_file_hash(path)


def test_source_tree_hash_is_deterministic(sealed_paths: ResearchPaths) -> None:
    assert get_source_tree_hash(sealed_paths.root) == get_source_tree_hash(sealed_paths.root)


def test_source_mutation_changes_source_tree_hash(sealed_paths: ResearchPaths) -> None:
    before = get_source_tree_hash(sealed_paths.root)
    source = sealed_paths.root / "research" / "momentum_v1" / "core.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert get_source_tree_hash(sealed_paths.root) != before


def test_strategy_parameter_mutation_changes_hash() -> None:
    changed = {name: dict(value) for name, value in STRATEGY_DEFINITIONS.items()}
    changed["AM_PRIMARY"]["lookback_months"] = 10
    assert get_strategy_definitions_hash(changed) != get_strategy_definitions_hash()


def test_cost_mutation_changes_hash() -> None:
    changed = dict(COST_MODEL)
    changed["round_trip_bps"] = [6.0, 10.0, 15.0]
    assert get_cost_model_hash(changed) != get_cost_model_hash()


def test_hashes_are_nonempty() -> None:
    import hashlib

    empty = hashlib.sha256(b"").hexdigest()
    assert get_strategy_definitions_hash() != empty
    assert get_cost_model_hash() != empty


def test_block_bootstrap_is_deterministic() -> None:
    returns = pd.Series(0.01, index=pd.date_range("2018-01-31", periods=24, freq="ME"))
    first = block_bootstrap(returns, "context", n_samples=20, block_size_months=3)
    second = block_bootstrap(returns, "context", n_samples=20, block_size_months=3)
    pd.testing.assert_frame_equal(first, second)


def test_bootstrap_context_changes_draws() -> None:
    values = [0.01, -0.02, 0.03, -0.01] * 6
    returns = pd.Series(values, index=pd.date_range("2018-01-31", periods=24, freq="ME"))
    first = block_bootstrap(returns, "one", n_samples=20, block_size_months=3)
    second = block_bootstrap(returns, "two", n_samples=20, block_size_months=3)
    assert not first.equals(second)


def _config() -> dict[str, object]:
    return {
        "periods": {
            "development": {"start": "2007-03-01", "end": "2016-12-31"},
            "diagnostic": {"start": "2017-01-01", "end": "2020-12-31"},
            "holdout": {"start": "2021-01-01", "end": "2025-12-31"},
        }
    }


def test_development_firewall() -> None:
    assert_public_period(_config(), "development", "2007-03-01", "2016-12-31")
    with pytest.raises(PermissionError):
        assert_public_period(_config(), "development", "2007-03-01", "2021-01-01")


def test_diagnostic_firewall() -> None:
    assert_public_period(_config(), "diagnostic", "2017-01-01", "2020-12-31")
    with pytest.raises(PermissionError):
        assert_public_period(_config(), "holdout", "2021-01-01", "2025-12-31")


def test_seal_requires_real_artifacts(sealed_paths: ResearchPaths) -> None:
    (sealed_paths.artifacts / "primary.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        create_seal(sealed_paths)


def test_valid_seal_round_trip(sealed_paths: ResearchPaths) -> None:
    created = create_seal(sealed_paths)
    verified = verify_seal(sealed_paths)
    assert verified["protocol_seal_hash"] == created["protocol_seal_hash"]


def test_source_mutation_invalidates_seal(sealed_paths: ResearchPaths) -> None:
    create_seal(sealed_paths)
    source = sealed_paths.root / "research" / "momentum_v1" / "core.py"
    source.write_text("MUTATED = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="HOLDOUT_INVALIDATED"):
        verify_seal(sealed_paths)


def test_config_mutation_invalidates_seal(sealed_paths: ResearchPaths) -> None:
    create_seal(sealed_paths)
    config = json.loads(sealed_paths.config.read_text(encoding="utf-8"))
    config["extra"] = "mutation"
    sealed_paths.config.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="HOLDOUT_INVALIDATED"):
        verify_seal(sealed_paths)


def test_dataset_mutation_invalidates_seal(sealed_paths: ResearchPaths) -> None:
    create_seal(sealed_paths)
    primary_path = sealed_paths.artifacts / "primary.parquet"
    primary = pd.read_parquet(primary_path)
    primary.iloc[0, 0] = 99.0
    primary.to_parquet(primary_path)
    with pytest.raises(ValueError, match="HOLDOUT_INVALIDATED"):
        verify_seal(sealed_paths)


def test_holdout_requires_seal(sealed_paths: ResearchPaths) -> None:
    with pytest.raises(FileNotFoundError, match="HOLDOUT_REQUIRES_VALID_SEAL"):
        open_holdout(sealed_paths, evaluator=lambda _paths, _config, _seal: {"ok": True})


def test_holdout_writes_marker_and_refuses_second_run(sealed_paths: ResearchPaths) -> None:
    create_seal(sealed_paths)
    output = open_holdout(sealed_paths, evaluator=lambda _paths, _config, _seal: {"synthetic": True})
    marker = json.loads(sealed_paths.marker.read_text(encoding="utf-8"))
    assert output["synthetic"] is True
    assert marker["status"] == "COMPLETED"
    assert marker["protocol_seal_hash"]
    with pytest.raises(RuntimeError, match="HOLDOUT_ALREADY_BURNED"):
        open_holdout(sealed_paths, evaluator=lambda _paths, _config, _seal: {"synthetic": True})
