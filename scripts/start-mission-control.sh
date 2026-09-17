#!/usr/bin/env bash
# Read-only dashboard. Broker mode always uses the configured runtime database.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ "${1:-}" == "--replay" ]]; then
  shift
  exec .venv/bin/python -m scripts.replay_live "$@"
fi
if [[ "${1:-}" == "--isolated" ]]; then
  echo "Isolated broker Mission Control is disabled; it could present fixture data as operational state." >&2
  exit 2
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--replay [--speed 0.5|1|5|20] [--port 8000]]" >&2
  exit 2
fi

export APP_ENV="local"
export DATABASE_ROLE="runtime"
export EXECUTION_MODE="alpaca_paper"
exec .venv/bin/python -m scripts.mission_control
