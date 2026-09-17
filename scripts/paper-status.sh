#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export APP_ENV="local"
export DATABASE_ROLE="runtime"
export EXECUTION_MODE="alpaca_paper"
exec .venv/bin/python -m scripts.paper_ops status
