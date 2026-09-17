#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
docker compose --profile test up -d postgres_test
echo "Dedicated test PostgreSQL: 127.0.0.1:55432/trading_bot_test"
echo "Run tests only through ./scripts/test-safe.sh"
