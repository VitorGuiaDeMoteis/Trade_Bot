# TradingBot Agent State

## Branch

agent/autonomous-dev

## Baseline

- Autonomous baseline commit: 72d37d8
- Source lineage: feat/m8-night-lab
- Runtime database: trading_bot_unified
- Canonical Alembic head: f2c8a51d9b10
- Runtime Alembic current was previously confirmed as f2c8a51d9b10
- Mission Control previously returned /health HTTP 200
- Alpaca environment is Paper-only

## Operating mode

AUTONOMOUS SOFTWARE DEVELOPMENT

The agent may autonomously:

- inspect code
- modify code
- write tests
- modify documentation
- improve developer tooling
- improve Mission Control
- improve reliability
- improve watchdog/recovery tooling
- make local commits

The agent may NOT autonomously:

- mutate Alpaca broker state
- activate real-money trading
- switch to live Alpaca endpoints
- delete/reset runtime databases
- modify credentials
- push Git changes

## Historical issue already resolved

A previous agent incorrectly:

- changed alembic.ini script_location
- created a top-level alembic/versions directory
- made irrelevant whitespace edits to tests/test_alpaca_guard.py

Those changes were manually removed.

Do not recreate them.

## Current objective

Continuously improve TradingBot toward a safe, reliable, observable long-running Paper V1 system.

## Work completed by autonomous agent

### Cycle: daily-loss circuit breaker baseline (FIXED)

Root cause of the previously "unresolved" suspected bug:

- services/alpaca_paper/worker.py derived the breaker baseline from the SAME
  account snapshot used for current equity:
  `last_equity = self._decimal(account.get("equity"), "equity")`
- Guard computes `last_equity - equity`, so the delta was ALWAYS 0.
  The daily-loss circuit breaker was effectively DEAD CODE in production,
  while its unit tests still passed (tests inject a distinct baseline).

Fix:

- Baseline now comes from the broker account's `last_equity`
  (previous trading-day close), which survives process restarts and rolls
  over at the broker session boundary. No new DB table or migration needed.
- Added `_optional_decimal` helper; a missing/unparsable baseline yields None
  and ExecutionGuard fails CLOSED on BUY while still allowing closing SELLs.
- New tests: tests/test_daily_loss_baseline.py

The earlier "baseline must survive process restarts" concern is resolved by
using broker-provided `last_equity` instead of RAM-only state.

### Cycle: daily-loss breaker fail-closed on missing equity (FIXED)

Same bug class as above, one level deeper -- inside the guard itself:

- `guard.py` computed `equity = Decimal(str(snapshot.get("equity", 0)))`, so a
  broker account payload without `equity` substituted an INVENTED 0.
- The delta `last_equity - equity` then compared a REAL baseline against a
  fabricated value. For any `last_equity < DAILY_LOSS_LIMIT` the delta stayed
  under the limit and the breaker was BYPASSED: a nearly-wiped account passed
  the daily-loss check on no information at all.

Fix:

- Added `ExecutionGuard._optional_decimal` (None on absent/unparsable/non-finite).
- The BUY branch now fails CLOSED when either side of the delta is unavailable:
  missing snapshot, missing/unparsable `equity`, or missing/zero `last_equity`.
- Fail-closed applies only to opening risk; closing SELLs are unaffected.
- New tests: tests/test_daily_loss_equity_missing.py (8 pure guard unit tests).

Both halves of the bug are now closed: the worker supplies an independent
baseline, and the guard refuses to compute a delta it cannot source.

## Active blockers

None known at initialization.

## Known environmental test failures (do NOT re-investigate each cycle)

Postgres is not running in the agent environment, so DB-backed tests fail at
fixture setup. These are NOT caused by agent code changes:

- psycopg OperationalError / ConnectionTimeout (test_paper_audit,
  test_alpaca_paper_incident, many others)
- RuntimeError: alpaca_paper_startup_refused_schema_not_at_head
- tests/test_alpaca_provider.py network smoke tests
- tests/test_replay_live.py: Windows FileNotFoundError (no ComSpec/SystemRoot)

Confirm any suspicious failure is DB/network at setup BEFORE blaming code.

## Next task

Candidate: audit the remaining guard fail-closed paths and in-flight/exposure
accounting for the same class of bug (a comparison whose two sides derive from
the same snapshot, making the delta constant). tests/test_daily_loss_baseline.py
and tests/test_daily_loss_equity_missing.py document the pattern.

Secondary candidate: add observability for a missing `last_equity`, since it now
silently forces all BUYs to fail closed with the same generic message as a
missing current equity; an operator cannot tell the two apart from logs.

To run tests, use the project venv python (see AGENT_LESSONS.md); the default
`python` on PATH has no pytest.

## Autonomous cycle incident (historical)

First autonomous cycle was interrupted before completion: investigation
expanded too far, a full-suite pytest baseline consumed excessive time, and
temporary experimental code was left in the worktree. It was discarded back to a
clean commit. The cycle size rules in AGENT_MISSION.md exist because of this.
The suspected daily-equity baseline issue it raised is now RESOLVED above.
