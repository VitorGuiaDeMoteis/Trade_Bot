#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

export APP_ENV="test"
export DATABASE_ROLE="test"
export POSTGRES_HOST="127.0.0.1"
export POSTGRES_PORT="55432"
export POSTGRES_DB="trading_bot_test"
export POSTGRES_USER="test_only"
export POSTGRES_PASSWORD="test_only"
export RUNTIME_POSTGRES_HOST="127.0.0.1"
export RUNTIME_POSTGRES_PORT="5432"
export RUNTIME_POSTGRES_DB="trading_bot_dev"
export TEST_POSTGRES_DB="trading_bot_test"
export RUN_DB_TESTS="1"
unset DATABASE_URL

if [[ "$POSTGRES_DB" == "$RUNTIME_POSTGRES_DB" || "$DATABASE_ROLE" != "test" ]]; then
  echo "REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE" >&2
  exit 2
fi

PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment missing: $PYTHON" >&2
  exit 2
fi

docker compose --profile test up -d postgres_test
for attempt in {1..30}; do
  if docker compose --profile test exec -T postgres_test \
    pg_isready -U test_only -d trading_bot_test >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "Test PostgreSQL did not become ready" >&2
    exit 1
  fi
  sleep 1
done

"$PYTHON" - <<'PY'
from services.api.config import Settings
from services.api.database import create_database_engine
from sqlalchemy import text

settings = Settings(_env_file=None)
engine = create_database_engine(settings)
try:
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "trading_bot_test"
finally:
    engine.dispose()
PY

"$PYTHON" -m alembic upgrade head
exec "$PYTHON" -m pytest "$@"
