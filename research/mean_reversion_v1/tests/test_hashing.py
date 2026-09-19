from pathlib import Path

from research.mean_reversion_v1.seal import hash_object


def test_config_mutation_invalidates_seal(tmp_path: Path) -> None:
    config1 = {"a": 1}
    config2 = {"a": 2}
    assert hash_object(config1) != hash_object(config2)


def test_strategy_mutation_changes_hash() -> None:
    # Just basic hash equivalence of JSON
    strat1 = {"Z_entry": -2.0}
    strat2 = {"Z_entry": -1.5}
    assert hash_object(strat1) != hash_object(strat2)


def test_cost_mutation_changes_hash() -> None:
    c1 = {"cost_bps": 10.0}
    c2 = {"cost_bps": 20.0}
    assert hash_object(c1) != hash_object(c2)


def test_source_mutation_invalidates_seal() -> None:
    source1 = {"file1.py": "a = 1"}
    source2 = {"file1.py": "a = 2"}
    assert hash_object(source1) != hash_object(source2)
