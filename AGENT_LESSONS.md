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

Second instance of the same class, inside the guard:

- `guard.py` used `Decimal(str(snapshot.get("equity", 0)))`. The `, 0` default
  fabricated a value, so a missing equity compared a REAL `last_equity` against
  an INVENTED 0. For any `last_equity < DAILY_LOSS_LIMIT` the delta stayed
  under the limit and the breaker passed on no information at all.

Lesson: `dict.get(key, default)` on a broker field used in a SAFETY comparison
is a silent fail-open. Any numeric used in a financial guard must be parsed
through a helper that returns None on absent/unparsable/non-finite input, and
the caller must branch on None instead of substituting a default.

Fixed via `ExecutionGuard._optional_decimal`; the BUY branch now fails closed
when either side of the delta is unavailable. Fail-closed applies to opening
risk only -- position-closing SELLs must keep working when data is missing.

## Guard in-flight / exposure accounting fail-closed (FIXED)

Third instance of the same bug class, in the guard's remaining numeric
accounting. Every unsourceable broker field was coerced to an INVENTED zero,
each of which under-counted risk:

- pending SELL with missing/unparsable `quantity` counted as 0 sold, so
  `available_qty = current_qty - 0` and a second SELL of the FULL position was
  approved -> oversell into a short position;
- pending BUY with missing/unparsable `requested_notional` contributed $0 to
  in-flight exposure;
- open position with missing `market_value` contributed $0 to total exposure,
  under-counting MAX_TOTAL_EXPOSURE;
- open position with missing `qty` was silently SKIPPED by the `qty > 0` filter
  in the exposure sum, excluding its exposure from the cap entirely.

Fix (all through the existing `ExecutionGuard._optional_decimal`):

- in-flight SELL quantity unknown -> SELL fails closed;
- in-flight BUY notional unknown -> BUY fails closed (was already partly there,
  now via the same parsed path);
- traded symbol position qty unknown -> BOTH sides fail closed;
- traded symbol position market_value unknown -> BUY fails closed only, so a
  SELL can still flatten a position;
- any other position with unreadable qty or market_value -> BUY fails closed.

Fail-closed scope is deliberate: SELL only requires `qty`; `market_value` is
required only for BUY. New tests:
tests/test_guard_in_flight_fail_closed.py (10 pure guard unit tests).

## Guard fail-closed invariants worth preserving

- BUY requires BOTH `last_equity` (baseline) and `snapshot["equity"]` (current).
- `last_equity` of 0 is treated as unavailable (falsy), not as a valid baseline.
- SELL paths never depend on the daily-loss data, so a degraded account can
  still be flattened.
- SELL needs only position `qty`; `market_value` is required only for BUY.
  Never add a shared precondition that blocks position-closing.
- A position dict whose `qty` cannot be read must NOT be dropped by a
  `if qty > 0` filter -- that silently removes its exposure from the cap.

## Testing on this Windows host

- The default `python` on PATH is Hermes' own 3.14 and has NO pytest.
- Use the project venv interpreter for every pytest/ruff/mypy run:
  C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-unified/.venv/Scripts/python.exe
  (run it with workdir set to the TradingBot-agent repo)
- Postgres is not running in the agent environment, so DB-backed tests fail at
  fixture setup with psycopg ConnectionTimeout. These are environmental.
  tests/test_replay_live.py also fails on Windows for lack of ComSpec/SystemRoot.
- Check whether a failure happens at SETUP before treating it as a regression.
