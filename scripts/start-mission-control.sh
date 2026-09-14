#!/usr/bin/env bash
# No order submission. Optional isolated, portable PostgreSQL for this workstation.
set -euo pipefail
MC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$MC_ROOT"

if [[ "${1:-}" == "--isolated" ]]; then
    MC_DIR="$MC_ROOT/.tools/mission-control"
    MC_PG="$MC_DIR/postgres/usr/lib/postgresql/18/bin"
    if [[ ! -x "$MC_PG/pg_ctl" ]]; then
        echo "Portable PostgreSQL absent. See docs/mission-control.md." >&2
        exit 1
    fi
    export LD_LIBRARY_PATH="$MC_DIR/postgres/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432
    export POSTGRES_USER=mission_control POSTGRES_DB=mission_control
    if [[ ! -f "$MC_DIR/pgdata/PG_VERSION" ]]; then
        mkdir -p "$MC_DIR/socket"
        chmod 700 "$MC_DIR" "$MC_DIR/socket"
        (umask 077; .venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))' > "$MC_DIR/password")
        "$MC_PG/initdb" -D "$MC_DIR/pgdata" -U "$POSTGRES_USER" \
            --auth-local=trust --auth-host=scram-sha-256 --pwfile="$MC_DIR/password" \
            --encoding=UTF8 --locale=C.UTF-8 > "$MC_DIR/initdb.log"
    fi
    export POSTGRES_PASSWORD
    POSTGRES_PASSWORD="$(cat "$MC_DIR/password")"
    if ! "$MC_PG/pg_ctl" -D "$MC_DIR/pgdata" status > /dev/null 2>&1; then
        "$MC_PG/pg_ctl" -D "$MC_DIR/pgdata" -l "$MC_DIR/postgres.log" \
            -o "-h 127.0.0.1 -p 55432 -k $MC_DIR/socket" -w start
    fi
    export PGPASSWORD="$POSTGRES_PASSWORD"
    if [[ "$("$MC_PG/psql" -h 127.0.0.1 -p 55432 -U mission_control -d postgres \
        -tAc "SELECT 1 FROM pg_database WHERE datname = 'mission_control'")" != "1" ]]; then
        "$MC_PG/createdb" -h 127.0.0.1 -p 55432 -U mission_control mission_control
    fi
    unset PGPASSWORD
    # Migrations only touch this isolated demo database, never the M7 database.
    .venv/bin/alembic upgrade head
elif [[ $# -ne 0 ]]; then
    echo "Usage: $0 [--isolated]" >&2
    exit 1
fi

exec .venv/bin/python -m scripts.mission_control
