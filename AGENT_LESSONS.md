# TradingBot Agent Lessons

Durable engineering memory for autonomous development.

## Repository

- Agent branch: agent/autonomous-dev
- Protected integration branch/worktree: integration/tradingbot-unified
- Autonomous baseline commit: 72d37d8

## Alembic

- Canonical script_location is %(here)s/infrastructure/docker/migrations
- Canonical migrations are infrastructure/docker/migrations/versions/
- Initial canonical head is f2c8a51d9b10
- Never create a competing top-level alembic/versions tree

## Runtime

- Runtime database was moved to trading_bot_unified
- Historical references to trading_bot_dev may be stale
- trading_bot_unified was previously confirmed at Alembic head f2c8a51d9b10
- Mission Control previously reached HTTP /health = 200

## Windows

- Host is Windows
- Do not assume WSL

Project Python:

C:\Users\vitor\OneDrive\Documentos\ChatGPT\TradingBot-unified\.venv\Scripts\python.exe

Git Bash:

C:\Program Files\Git\bin\bash.exe

## Alpaca

Paper-only Trading API:

https://paper-api.alpaca.markets/v2

Never introduce a live-money trading endpoint.

## Source-of-truth hierarchy

Use:

1. verified runtime evidence for current operational state
2. Git HEAD for committed architecture
3. current tests/code
4. historical documentation

Historical handoff documents may be stale.

Uncommitted local files are not automatically canonical.

## Agent behavior

- Prefer small validated improvements
- Test before commit
- Never commit knowingly broken work
- Investigate uncertainty instead of inventing facts
- Keep durable lessons concise
- Avoid repeatedly rediscovering known facts

## Autonomous cycle sizing

- The first autonomous cycle became too large: it ran a full pytest suite, used many tool calls and repeatedly compacted context.
- Full-suite baseline testing must not happen at the beginning of every cycle.
- Prefer targeted tests and targeted file reads.
- Repeated context compression means the task must be split.
- Never temporarily reintroduce a known bug into tracked production code to prove a regression test.
- A cycle may finish with investigation only; the next clean cycle can implement the fix.

## Bug class: constant-delta comparison from one snapshot

The daily-loss circuit breaker was DEAD CODE in production:

- worker.py passed the SAME account snapshot as both the current equity and
  the baseline: `last_equity = self._decimal(account.get("equity"), "equity")`
- ExecutionGuard computes `last_equity - equity`, so the delta was always 0.
- Unit tests PASSED because tests/test_alpaca_guard.py injects a distinct
  `last_equity` directly into the guard. Tests of the guard did not cover the
  worker that feeds it.

Lesson: when a safety check takes a "baseline" and a "current" value, verify at
the CALL SITE that the two are independently sourced. A guard can be correct
and still be defeated by a caller. Test the wiring, not just the unit.

Fixed by using the broker account's `last_equity` (previous trading-day close),
which is restart-safe and rolls over at the session boundary. Alpaca's /account
payload is returned raw by AlpacaPaperAdapter.get_account, so fields such as
`last_equity`, `daytrade_count` and `buying_power` are available without new
DB tables or migrations.

## Testing on this Windows host

- The default `python` on PATH is Hermes' own 3.14 and has NO pytest.
- Use the project venv interpreter for every pytest/ruff/mypy run:
  C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-unified/.venv/Scripts/python.exe
  (run it with workdir set to the TradingBot-agent repo)
- Postgres is not running in the agent environment, so DB-backed tests fail at
  fixture setup with psycopg ConnectionTimeout. These are environmental.
  tests/test_replay_live.py also fails on Windows for lack of ComSpec/SystemRoot.
- Check whether a failure happens at SETUP before treating it as a regression.
