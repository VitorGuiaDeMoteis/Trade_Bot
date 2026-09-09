#!/bin/bash
set -e
PROJECT_ROOT="$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")"

if [ ! -f "$PROJECT_ROOT/.tools/flutter/bin/flutter" ]; then
    echo "Flutter portatil ausente. Execute: ./scripts/install-flutter.sh" >&2
    exit 1
fi
export PATH="$PROJECT_ROOT/.tools/flutter/bin:$PATH"

run_checked() {
    if ! "$@"; then
        echo "Comando falhou: $1"
        exit 1
    fi
}

cd "$PROJECT_ROOT"
run_checked uv sync --locked
run_checked uv run ruff format --check .
run_checked uv run ruff check .
run_checked uv run mypy
run_checked uv run pytest -m "not integration"
run_checked docker compose config --quiet

if [ "$1" == "--database" ]; then
    run_checked docker compose --profile test up -d --wait postgres_test
    export RUN_DB_TESTS="1"
    run_checked uv run pytest -m integration
fi

cd apps/mobile_app
run_checked flutter pub get --enforce-lockfile
run_checked dart format --output=none --set-exit-if-changed lib test integration_test test_driver
run_checked flutter analyze --fatal-infos --fatal-warnings
run_checked flutter test
