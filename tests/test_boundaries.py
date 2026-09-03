"""Evita acoplamento prematuro das fronteiras documentadas."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "folder",
    [
        "services/market_simulator",
        "services/strategy_engine",
        "services/risk_engine",
        "services/paper_executor",
        "packages/domain",
        "packages/contracts",
    ],
)
def test_modules_do_not_import_other_services_or_http_framework(folder):
    for path in (ROOT / folder).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"Use imports absolutos para auditar fronteiras: {path}"
                modules = [node.module or ""]
            for module in modules:
                assert module.split(".")[0] not in {"services", "fastapi", "sqlalchemy", "psycopg"}
