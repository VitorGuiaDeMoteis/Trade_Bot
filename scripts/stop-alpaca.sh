#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export APP_ENV="local"
export DATABASE_ROLE="runtime"
export EXECUTION_MODE="alpaca_paper"

.venv/bin/python -m scripts.paper_ops pause

PID_FILE="$PROJECT_ROOT/.runtime/alpaca-paper.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "PAUSE confirmado; nenhum PID de runtime registrado."
  exit 0
fi

runtime_pid="$(tr -cd '0-9' < "$PID_FILE")"
if [[ -z "$runtime_pid" ]] || ! kill -0 "$runtime_pid" 2>/dev/null; then
  echo "PAUSE confirmado; runtime já estava encerrado."
  exit 0
fi

kill -TERM "$runtime_pid"
for _ in {1..30}; do
  if ! kill -0 "$runtime_pid" 2>/dev/null; then
    echo "PAUSE confirmado; runtime encerrado de forma graciosa."
    exit 0
  fi
  sleep 1
done

echo "PAUSE confirmado, mas o runtime não encerrou em 30 segundos (PID $runtime_pid)." >&2
exit 1
