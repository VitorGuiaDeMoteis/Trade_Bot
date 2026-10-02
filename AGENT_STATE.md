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

### Cycle: guard in-flight/exposure fail-closed accounting (FIXED)

Third and last instance of the same bug class, in the guard's remaining
numeric accounting. Unsourceable broker fields were coerced to invented zeros
that under-counted risk:

- pending SELL with missing `quantity` counted as 0 sold, so `available_qty`
  stayed at the full position size and a second SELL of the whole position was
  approved -> oversell into a short;
- pending BUY with missing `requested_notional` contributed $0 in-flight;
- open position with missing `market_value` contributed $0 to total exposure;
- open position with missing `qty` was skipped by the `qty > 0` filter, so its
  exposure never entered the cap.

Fix: all four now route through `ExecutionGuard._optional_decimal` and fail
closed. Scope kept narrow so closing risk is never blocked: SELL requires only
position `qty`; `market_value` is required only for BUY.

New tests: tests/test_guard_in_flight_fail_closed.py (10 pure guard unit
tests). Targeted suite 32 passed; ruff and mypy clean.

## Cycle bookkeeping

The guard in-flight/exposure fix above was finished in a prior cycle but left
uncommitted; a recovery-mode cycle re-validated it (32 targeted tests, ruff,
mypy) and committed it. The tree was clean at the start of the next cycle.

### Cycle: daily-breaker fail-closed reason observability (DONE)

- `guard.py` returned ONE string ("Equity indisponível para checagem do Daily
  Breaker") for two distinct causes: an unsourceable baseline (`last_equity`
  absent/zero) and an unsourceable current `equity`. An operator reading only
  the rejection reason could not tell them apart, and they have different
  remediations.
- Both branches now keep the shared "Equity indisponível" prefix and append the
  failing side: `(baseline last_equity ausente ou inválido)` vs
  `(equity atual ausente ou inválido no snapshot da corretora)`.
- NO safety semantics changed: both paths still fail CLOSED on BUY, SELL is
  still unaffected, and the genuine `Circuit breaker diário` message is
  untouched. Keeping the common prefix preserves existing log greps.
- New tests: tests/test_daily_loss_breaker_reason_observability.py (10 pure
  guard unit tests). Targeted 37 passed; ruff clean; mypy clean on the
  configured production scope.

### Cycle: worker broker-numeric fail-closed accounting (FIXED)

Final unreviewed layer of the `dict.get(key, 0)` fail-open bug class -- the
worker's own broker-numeric accounting rather than the guard's. Three call
sites passed a `, 0` default into `self._decimal`, which DEFEATED the helper:
`dict.get` returned an INVENTED 0 for a missing key, so `_decimal` succeeded
and the fabricated value flowed on.

- `pending_sell_quantity` (`_process_pending_submits`): a pending SELL row with
  a NULL quantity summed as 0 sold, so `available_qty` was overstated and a
  second SELL of the whole position would be sized correctly only by accident.
  Defense-in-depth: `ExecutionGuard.evaluate` already fails closed on an
  unsourceable in-flight SELL quantity BEFORE this line runs, so it was not a
  live fail-open.
- `buying_power` and `unrealized_pl` (`_save_broker_snapshot`): an absent field
  wrote a plausible-looking 0 into `broker_portfolio_snapshots`, so Mission
  Control displayed a real-looking ACTIVE account with no buying power and zero
  unrealized P/L -- wrong numbers presented as authoritative.

Fix: all three pass the raw `dict.get(key)`, matching the convention already
used by every sibling field in the same functions (`cash`, `equity`,
`portfolio_value`, `qty`, `market_value`, `avg_entry_price`, `current_price`
all already raised). A missing field now reaches `_decimal` and fails the
cycle closed as `invalid_broker_<field>`, which `_run` turns into DEGRADED.
This is fail-CLOSED and never permissive: a broker payload too poor to
account for is not allowed to publish an invented balance.

Deliberate decision on `buying_power` (schema is NOT NULL): raise rather than
allow NULL. Allowing NULL would require a migration and would leave the
snapshot row's real-vs-absent status invisible in Mission Control, whereas
raising is already the behavior for the three sibling account fields and needs
no schema change.

New tests: tests/test_worker_broker_numeric_fail_closed.py (7 pure unit tests,
stub engine, no Postgres/broker/DB mutation). Targeted 7 passed; sibling guard
suites 27 passed; ruff clean; mypy clean on `services/alpaca_paper`.

### Cycle: worker pending-SELL sizing arithmetic now unit tested (DONE)

The last untested trading-decision path in the worker. `_process_pending_submits`
computes the only share quantity the bot ever sends for a position-closing SELL:

    quantity = broker_quantity - pending_sell_quantity   (worker.py:404-422)

Two independent failure directions, both financially material: too large
oversells into a short, too small leaves dust. `tests/test_alpaca_worker.py`
touches this method only via DB-backed tests that cannot run without Postgres,
so the arithmetic had NO pure unit coverage (the prior cycle only asserted the
`_decimal` contract, not the arithmetic that consumes it).

No production code changed. New test file
tests/test_worker_pending_sell_sizing.py (13 pure unit tests, scripted engine +
recording executor, no Postgres/broker/DB mutation) covers:

- full position when nothing is in flight (10 -> 10);
- subtraction of a single pending SELL (10 - 4 -> 6) and of SEVERAL (10 - 3 -
  2.5 -> 4.5), the case a single-order assumption would get wrong;
- a pending SELL for a DIFFERENT symbol is not subtracted, and a pending BUY
  never reduces a SELL;
- a pending SELL covering the whole position, or exceeding it, is rejected and
  NOTHING is submitted;
- an in-flight SELL with NULL quantity fails closed (no submission);
- a SELL with no position, and a position whose qty cannot be sourced, are
  rejected before any submit;
- a SELL submit carries `notional=None`;
- a degraded worker and a paused system_controls row submit nothing.

`ExecutionGuard.evaluate` runs for real inside these tests, so the rejection
assertions double as wiring coverage of the guard's SELL branch.

Validation: 13 new passed; sibling guard/worker suites 48 passed; ruff clean.
mypy not run -- no production change (tests/ is outside the configured scope).

### Cycle: worker BUY notional sizing now unit tested (DONE)

The remaining half of the only method that turns an APPROVED risk decision into
an order. The previous cycle covered the SELL branch only, and the two sides
share one guard call and one submit call, so a BUY-side mistake was invisible to
the SELL tests.

`worker.py:424-426` sends a DOLLAR order for a BUY -- `quantity = Decimal("0")`
and `notional = ExecutionGuard.MAX_NOTIONAL_PER_TRADE` -- and had NO pure unit
coverage. No production code changed. New test file
tests/test_worker_pending_buy_notional.py (15 pure unit tests, scripted engine +
recording executor, no Postgres/broker/DB mutation) covers:

- a BUY submits `notional == MAX_NOTIONAL_PER_TRADE` and `quantity == 0`, i.e.
  never a share quantity;
- the submitted notional is asserted against the guard CONSTANT, not a literal
  10.00, because the guard charges that same constant against
  `MAX_TOTAL_EXPOSURE` (guard.py:160-168). If the two ever diverged, the cap
  would be enforced against a figure no order used;
- exposure cap boundary both ways: existing exposure making the total exactly
  `MAX_TOTAL_EXPOSURE` is APPROVED, one cent more is REJECTED;
- an in-flight BUY's `requested_notional` counts toward the cap (boundary + over
  + unsourceable notional -> fail closed);
- no pyramiding with an open position, no pyramiding with a pending in-flight BUY;
- another position with unsourceable `market_value` or unsourceable `qty` fails
  the BUY closed;
- a missing `last_equity` baseline and a tripped daily breaker reject the BUY;
- a symbol outside `ALLOWED_SYMBOLS` is rejected;
- a SELL still submits `quantity=10, notional=None` under the SAME degraded
  account, pinning that fail-closed is BUY-only.

`ExecutionGuard.evaluate` runs for real in all of them, so the rejections double
as wiring coverage of the guard's BUY branch.

Validation: 15 new passed; guard/worker sibling suites 61 passed; ruff clean.
mypy not run -- no production change (tests/ is outside the configured scope).

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

The `dict.get(key, 0)` broker-numeric audit is COMPLETE across both layers
(guard d55774e/6747abe, worker cc0acf5). Both branches of the worker's order
builder are now covered by pure unit tests (SELL sizing 04b0f9f, BUY notional
coverage added this cycle).

Candidate next tasks (pick one in a clean cycle):

- Verify `broker_portfolio_snapshots.buying_power` NOT NULL assumption still
  holds in the current migration head (f2c8a51d9b10) before relying on the
  raise-not-NULL decision from the worker broker-numeric cycle. Grep the
  migrations directory, no DB access needed.
- Audit `services/alpaca_paper/executor.py` for the same bug class: any broker
  numeric read there with a `dict.get(key, default)` default, and whether
  `broker_order_quantity_divergence` (worker.py:255) has coverage.
- `_process_pending_submits` raises `RuntimeError("sell_quantity_unavailable")
  when computed qty <= 0 (worker.py:421-422). Check whether an unreachable
  throw there would kill the whole worker cycle (`_run` turns RuntimeError into
  DEGRADED) rather than just skipping one decision -- a single bad pending SELL
  degrading the entire bot is an availability concern, unlike the intended
  financial fail-closed.

To run tests, use the project venv python (see AGENT_LESSONS.md); the default
`python` on PATH has no pytest.

## Autonomous cycle incident (historical)

First autonomous cycle was interrupted before completion: investigation
expanded too far, a full-suite pytest baseline consumed excessive time, and
temporary experimental code was left in the worktree. It was discarded back to a
clean commit. The cycle size rules in AGENT_MISSION.md exist because of this.
The suspected daily-equity baseline issue it raised is now RESOLVED above.
