#!/usr/bin/env bash
set -euo pipefail
MC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$MC_ROOT"

echo "Executando preflight do ALPACA PAPER V1..."
export APP_ENV="local"
export DATABASE_ROLE="runtime"
export EXECUTION_MODE="alpaca_paper"
if [[ -f ".runtime/alpaca-paper.pid" ]]; then
  existing_pid="$(tr -cd '0-9' < .runtime/alpaca-paper.pid)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Runtime Alpaca Paper já está ativo (PID $existing_pid)" >&2
    exit 1
  fi
fi
docker compose up -d postgres
.venv/bin/python -m scripts.paper_ops preflight
echo "Preflight concluído; iniciando API + worker em Alpaca PAPER."
exec .venv/bin/python scripts/_run_alpaca.py
