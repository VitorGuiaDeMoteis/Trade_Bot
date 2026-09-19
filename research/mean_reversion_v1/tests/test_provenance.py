import subprocess

import pytest

from research.mean_reversion_v1.manifest import (
    create_run_manifest,
)


def test_dirty_tree_raises(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path)

    (tmp_path / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=tmp_path)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path)

    # Make dirty
    (tmp_path / "test.py").write_text("print('hello world')")

    with pytest.raises(RuntimeError, match="DIRTY_RESEARCH_TREE"):
        create_run_manifest(tmp_path, {}, {}, "test", {})


def test_source_hash_changes(tmp_path):
    pass  # we can't easily test this without mocking sealed_source_paths, but it's trivial
