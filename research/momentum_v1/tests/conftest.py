from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.momentum_v1.seal import ResearchPaths


@pytest.fixture
def market_data() -> pd.DataFrame:
    dates = pd.bdate_range("2018-01-02", "2021-03-31")
    data = pd.DataFrame(index=dates)
    symbols = ["A", "B", "C", "D"]
    growth = {"A": 0.0008, "B": 0.0005, "C": 0.0002, "D": -0.0002}
    for symbol in symbols:
        close = 100.0 * np.cumprod(np.full(len(dates), 1.0 + growth[symbol]))
        data[("Open", symbol)] = close * 0.999
        data[("Close", symbol)] = close
    data[("Close", "DTB3")] = 2.0
    return data


def _write_primary(path: Path) -> None:
    dates = pd.bdate_range("2019-12-30", "2021-01-29")
    columns = [
        (field, symbol)
        for symbol in ["SPY", "EFA", "EEM", "TLT", "GLD", "DBC", "VNQ"]
        for field in ("Open", "Close")
    ]
    data = pd.DataFrame(100.0, index=dates, columns=pd.MultiIndex.from_tuples(columns))
    data.to_parquet(path)


@pytest.fixture
def sealed_paths(tmp_path: Path) -> ResearchPaths:
    root = tmp_path / "repo"
    package = root / "research" / "momentum_v1"
    docs = root / "docs"
    artifacts = root / ".artifacts" / "research" / "momentum_v1"
    package.mkdir(parents=True)
    docs.mkdir()
    artifacts.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "base"],
        cwd=root,
        check=True,
    )
    base_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    config = {
        "protocol_version": "1.3",
        "base_git_sha": base_sha,
        "universe": ["SPY", "EFA", "EEM", "TLT", "GLD", "DBC", "VNQ"],
        "data": {"start_date": "2019-12-30", "end_date": "2021-01-29", "first_valid_signal": "2020-12-31"},
        "periods": {
            "development": {"start": "2020-01-01", "end": "2020-06-30"},
            "diagnostic": {"start": "2020-07-01", "end": "2020-12-31"},
            "holdout": {"start": "2021-01-01", "end": "2021-01-29"},
        },
    }
    (package / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (package / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (docs / "MOMENTUM_EXPERIMENT_V1_3.md").write_text("protocol 1.3\n", encoding="utf-8")
    (root / "uv.lock").write_text("lock\n", encoding="utf-8")
    _write_primary(artifacts / "primary.parquet")
    fred_dates = pd.bdate_range("2019-12-30", "2021-01-29")
    fred = pd.DataFrame(1.0, index=fred_dates, columns=pd.MultiIndex.from_tuples([("Close", "DTB3")]))
    fred.to_parquet(artifacts / "fred_dtb3.parquet")
    _write_primary(artifacts / "alpaca_crosscheck.parquet")
    _write_primary(artifacts / "substitutes.parquet")
    return ResearchPaths(root=root, artifacts=artifacts)
