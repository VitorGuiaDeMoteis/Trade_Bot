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

### Cycle: executor broker-numeric fail-closed accounting (FIXED)

The last production module holding the `dict.get(key, "0")` bug class. In the
executor the fabricated zero was worse than cosmetic: `reconcile_order` gates
fill persistence on `if filled_qty > 0 and actual_broker_id`, so an invented 0
skipped the ENTIRE `get_fills` block and real fills were never written to
`broker_fills` -- the local ledger silently under-reported execution while the
order still showed the broker's status.

Fixed via a new `AlpacaPaperExecutor._required_decimal` (raises
`RuntimeError("invalid_broker_<field>")` on absent / None / empty / unparsable /
non-finite) applied at four sites:

- `filled_qty` in `_handle_timeout_or_disconnect` (executor.py:59) -- the
  idempotent retry path after a submit timeout, where proving absence of the
  order is the whole point;
- `filled_qty` in `reconcile_order` (executor.py:266);
- per-fill `qty`/`price` in `reconcile_order` (executor.py:294-295), labelled
  `fill_quantity`/`fill_price` so the reason names which side failed.

Both order-level parses run BEFORE `engine.begin()`, so an untrustworthy payload
cannot half-persist a status update. Raising propagates to `worker._run`, which
already maps any exception to `_enter_degraded` + retry next cycle, so this is
fail-CLOSED, never permissive.

Deliberately NOT changed: `filled_quantity=Decimal("0")` on the fresh-submit
insert (executor.py:152) is a real literal meaning "no fill yet", not a parsed
broker value; `fee` keeps its allow-None + swallow-on-parse-error handling
because a fee is optional and `None` is meaningful in `broker_fills`.

New tests: tests/test_executor_broker_numeric_fail_closed.py (11 pure unit
tests, stub adapter + recording engine, no Postgres/broker/DB mutation).
Validation: 11 new passed; executor + guard/worker siblings 72 passed; ruff
clean; mypy clean on `services/alpaca_paper`. The 3 errors in
tests/test_alpaca_executor.py are the known psycopg/Postgres environmental
setup failures; `test_reconcile_order_partially_filled` was read to confirm its
mocked payload supplies `filled_qty` and per-fill `qty`/`price`, so the new
parse does not break it when Postgres is available.

This closes the `dict.get(key, default)` audit across all three production
layers (guard, worker, executor).

### Cycle: broker portfolio reported 0 orders/fills (FIXED)

Found by the mandatory Paper review gate, NOT from the backlog. The live Paper
observation carries a deliberate mismatch check and it was failing:

    orders_count_reported: 0  vs  orders_count_actual: 7
    fills_count_reported: 0   vs  fills_count_actual: 7

Runtime itself was healthy (ACTIVE, not paused, not degraded, reconciled, one
open SPY position, unrealized P&L -0.005916), so the anomaly was purely an
observability defect, not a trading fault.

Root cause: `get_broker_portfolio` built a `PaperPortfolio` without passing
`orders_count`/`fills_count` at all, so the contract defaults (`= 0` in
packages/contracts/paper.py:100-101) silently published 0 while the SAME
payload carried fully populated `orders`/`fills` lists. Any operator or agent
reading Mission Control would conclude the paper run had never traded.

The naive fix (`orders_count=len(b_orders)`) would still be wrong: both lists
are `LIMIT 100`, so once the run exceeds 100 rows the count would silently
freeze at 100 -- a worse lie than 0 because it looks plausible.

Fix: `conn.scalar(select(func.count()).select_from(j))` for orders over the
SAME `broker_orders JOIN paper_orders` join the list uses, and the same for
`broker_fills`. `or 0` guards the None case. Count semantics stay aligned with
list semantics (both unscoped by run_id, exactly as before) -- this changes no
trading behavior, only the reported totals.

New tests: tests/test_broker_portfolio_counts.py (3 pure unit tests, stub
connection dispatching on the statement text; no Postgres/broker/DB mutation).
They pin the real totals, assert the counts do NOT collapse to the capped list
length, and cover the empty-state 0 case.

Validation: 3 new passed; ruff clean; mypy clean on broker_routes.py.

### Cycle: broker portfolio `requested_at` is submit time, not reconcile time (FIXED)

Started as RECOVERY MODE: the worktree was dirty with an uncommitted
`requested_at` correctness fix in `services/api/broker_routes.py` plus its
tests. The production change was right; the sibling pure-unit fixture
predated the new column and raised `KeyError: 'requested_at'`. Completed and
committed it.

The route built `PaperOrder.requested_at=o["last_reconciled_at"]` -- i.e. it
reported the BROKER RECONCILE time as the order's request time. But
`broker_orders.last_reconciled_at` is bumped on every reconcile cycle, and the
fills returned in the same payload carry `filled_at` derived from the real
submit time. The reported order time therefore drifted forward on every
reconcile, so Mission Control could show a fill that appears to have happened
BEFORE the order that produced it. `paper_orders.requested_at` is the
authoritative immutable submit time and is already joined in this query.

Fix (services/api/broker_routes.py): select `paper_orders.c.requested_at` in
the existing `broker_orders JOIN paper_orders` query and map it to
`PaperOrder.requested_at`; keep `last_reconciled_at` in its own contract field
(`PaperOrder.last_reconciled_at`, already optional) instead of discarding it.
No schema change, no broker call, no trading-behavior change -- only which
timestamp a read endpoint reports.

New/updated tests:
- tests/test_broker_portfolio_counts.py: `_order_row` now carries
  `requested_at` deliberately DISTINCT from `last_reconciled_at` (2h apart), so
  a test can tell which one the route reported; added 2 pure unit tests pinning
  that `requested_at` is submit time, that a fill never precedes its own order,
  and that re-reconciling never moves `requested_at` (file total 5 pure tests).
- tests/test_broker_routes.py: added a DB-backed sibling regression test
  mirroring the existing fee-none test, plus made its fill-vs-order comparison
  parse ISO strings into datetimes (raw string compare is flaky because ISO
  renderings differ by fractional-second presence).

Validation: 16 targeted passed (test_broker_portfolio_counts.py 5 +
test_health_paper_worker_ready.py 11); ruff clean on both files I changed
(test_broker_routes.py retains 7 PRE-EXISTING ruff errors also present on HEAD
-- the WIP added 1 and it was fixed; confirmed by re-running ruff against a
`git stash`ed tree); mypy clean on broker_routes.py. The new DB-backed test in
test_broker_routes.py COLLECTS (2 tests) but cannot execute here: the whole
file times out at 120s because Postgres is down -- the known environmental
condition, not a code fault. Its pure-unit equivalent in
test_broker_portfolio_counts.py carries the executable coverage.

Recovery-cycle verification re-run: 16 targeted pure tests green
(test_broker_portfolio_counts.py 5 + test_health_paper_worker_ready.py 11),
mypy clean on broker_routes.py, ruff clean on broker_routes.py and
test_broker_portfolio_counts.py. The 7 ruff findings in
tests/test_broker_routes.py all land at lines 1-82, entirely in the pre-existing
region (the WIP starts at line 145), so the WIP added none -- confirming the
claim above. NOTE the earlier method recorded for that check was unsound: running
ruff on a `git show HEAD:` dump in a temp dir loses the repo pyproject config, so
it reported 1 error instead of 7. Verify by line-number location inside the repo,
not via an out-of-tree copy.

PAPER_REVIEW (this cycle): status ACTIVE, paused=false, degraded=false,
reconciled=true, open positions [TSLA], orders reported 0 vs actual 9, fills
reported 0 vs actual 9, unrealized P&L 9.97 (equity 99951.32 / cash 99941.35),
health "ok", last_reconciled_at 2026-10-02T18:21:16Z. The 0-vs-N reported-count
mismatch persists only because the fixes are not deployed to the frozen runtime
(deploy needs human approval) -- no new actionable Paper anomaly.

One new observation worth a future cycle: every order in the observation payload
carries `"last_reconciled_at": null` while the portfolio-level
`last_reconciled_at` is populated. The broker route fixed by this WIP now sets
that field, so the null most likely originates in the OBSERVATION builder path
(services/alpaca_paper/observation.py or its snapshot builder), not in the route.
Worth identifying which constructor emits the observation payload so a later
deploy cannot publish another null timestamp through a second path.

### Cycle: /health no longer flaps in ALPACA PAPER (FIXED)

Found by the mandatory Paper review gate, finished and committed in recovery
mode after an earlier cycle left the change uncommitted.

Runtime evidence: 14 of 41 observation samples reported `health.status=
degraded` while `paper.degraded=false`, `reconciled=true` and `paused=false`,
every one taken 3.06-3.92s after that sample's own `last_reconciled_at` -- i.e.
inside the NEXT cycle's fail-closed window, not a real fault.

Root cause: `reconcile_once` deliberately sets `reconciliation_ready=False`,
`degraded=True`, `degraded_reason="reconciliation_in_progress"` at the top of
every 3s cycle so no order can be placed against half-refreshed broker state.
That is the EXECUTION gate, but `/health` read it as a health signal and
returned 503 for a slice of every cycle in a healthy runtime. Mission Control
inherits the flap (mission-control.html:134 keys on `health.status!=='ok'`), so
this was also a false-DEGRADED operator signal on a real Paper run.

Fix, deliberately splitting the two concepts:

- new `AlpacaPaperWorker.health_ready()` -- the RUNTIME fault signal. It fails
  closed when `has_reconciled` is False (no verified broker picture yet) or
  when `degraded_reason` is a real error rather than the in-progress sentinel.
- new durable `has_reconciled` latch: set True only by a successful
  `reconcile_once`, set False by `_enter_degraded`. Without the latch the next
  cycle's in-progress sentinel would self-heal a runtime failing every cycle.
- `/health` now calls `health_ready()`.
- NO trading path changed: worker.py:313, 359 and 423 still gate on
  `degraded` / `reconciliation_ready`, so the in-progress window still submits
  nothing. `health_ready()` had exactly one caller.

Second, smaller defect in the same handler: `response.status_code` was set
BEFORE the ALPACA PAPER worker check narrowed `ready`, so the endpoint could
return HTTP 200 alongside a body saying "degraded". Now every verdict is
computed first and the status code assigned once.

New tests: tests/test_health_paper_worker_ready.py (11 pure unit tests, stub
engine + TestClient, no Postgres/broker/DB mutation), including one that pins
healthy != allowed-to-trade and one that a fault cannot self-heal.

Validation: 11 new passed; health/mission-control/observer/paper_stop siblings
39 passed, 5 skipped; ruff clean; mypy clean on the two changed files. The 3
failures in tests/test_mission_control.py are the known environmental
`alpaca_paper_startup_refused_schema_not_at_head` (Postgres down), unchanged by
this work.

### Cycle: `_assert_open_orders_known` fail-closed coverage (DONE, recovery mode)

Finished a WIP left uncommitted by a previous cycle: an untracked pure unit test
file for `AlpacaPaperWorker._assert_open_orders_known` (worker.py:231-284), the
one reconciliation check that NEVER repairs anything and only raises. It runs on
EVERY cycle (worker.py:150), between order reconciliation and the snapshot save,
and any raise becomes `_enter_degraded` via `_run`, which releases no new
execution for the rest of the process lifetime.

The WIP was 16/17 green. The single failure was a FIXTURE bug, not a production
defect: `test_one_known_order_does_not_mask_a_second_unknown_one` built two
remote orders that both defaulted to `client_order_id=CLIENT_ID`, so the second
one legitimately matched by client id through the broker-id fallback
(`by_broker_id.get(id) or by_client_id.get(client_id)`). Fixed by giving the
second order its own `client_order_id`, which is what Alpaca actually does.

No production code changed. New file
tests/test_worker_reconcile_unknown_open_orders.py (17 pure unit tests, scripted
connection + canned local rows; no Postgres/broker/DB mutation) pins every
branch: no-open-orders is safe, BUY compares notional, SELL compares quantity,
match by client id when the broker id is not stored yet, case-insensitive
symbol/side, and raises for unknown order, missing id, symbol divergence, side
divergence, terminal-status divergence (the double-exposure case), notional and
quantity divergence (including a missing numeric on EITHER side), and an
unparsable remote size surfacing as `invalid_broker_open_order_notional`.

Validation: 17 new passed; worker sibling suites 35 passed; ruff clean. mypy
not run -- no production change (`tests/` is outside the configured scope).

### Cycle: broker portfolio orders sorted by reconcile time (FIXED, recovery mode)

Started as RECOVERY MODE: dirty tree with an uncommitted ORDER BY fix in
services/api/broker_routes.py plus 2 pure unit tests. The change was right;
this cycle verified it end-to-end and committed it.

The query sorted `portfolio.orders` by
`broker_orders.last_reconciled_at DESC` -- a field that is a PER-CYCLE
HEARTBEAT, re-stamped every reconciliation (executor.py:69, :89, :153, :215),
not a record of when anything happened. An order still working at the broker
therefore keeps the newest timestamp forever and floats to the top of the list
permanently, so Mission Control's newest-first order list was not newest-first
at all -- and it directly contradicted the `requested_at` this same payload
reports (fixed in a previous cycle). With `LIMIT 100`, a run with old orders
still open can also have its genuinely newest trades pushed out of the window.

Fix: order by `paper_orders.requested_at DESC` (the immutable submit time
already selected for the response field), plus `paper_orders.symbol` and
`paper_orders.order_id` as tiebreakers. `paper_orders.order_id` is the PRIMARY
KEY and `symbol`/`requested_at` are NOT NULL (migration 0008), so the sort is a
total order and the LIMIT 100 window is deterministic rather than shuffled.
Read-only query change: no schema change, no broker call, no trading behavior.

New tests (tests/test_broker_portfolio_counts.py, now 7 pure unit tests): the
ORDER BY must start at `paper_orders.requested_at DESC` and must NOT mention
`last_reconciled_at`; and the window must carry a total-order tiebreaker.

Validation: 7 new-file tests passed; broker portfolio + health siblings 18
passed; ruff clean on both changed files; mypy clean on broker_routes.py.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health ok, open positions [TSLA], orders reported 0 vs actual 9, fills reported
0 vs actual 9, unrealized P&L -0.0235810000 (equity 99951.32 / cash 99941.35),
last_reconciled_at 2026-10-02T18:35:17Z. The 0-vs-N mismatch persists only
because the agent-side fixes are not deployed to the frozen runtime (deploy
needs human approval) -- no new actionable Paper anomaly.

Still open from the previous cycle and CONFIRMED again here: every
`latest_orders[*]` entry in the observation payload has
`"last_reconciled_at": null` while the portfolio-level `last_reconciled_at` is
populated. Since the broker route now supplies that field, the null must come
from the OBSERVATION builder path -- see next-task note below.

### Cycle: unexecutable SELL degrades the whole worker (FIXED, recovery mode)

Started as RECOVERY MODE: dirty tree with an uncommitted change to
`services/alpaca_paper/worker.py` and 3 pure unit tests in
`tests/test_worker_pending_sell_sizing.py`. The change was correct and
fail-closed; this cycle validated it end-to-end and committed it.

`_process_pending_submits` raised
`RuntimeError("sell_quantity_unavailable:{symbol}")` when the computed SELL
quantity was `<= 0` (worker.py:453). `_run` turns ANY RuntimeError into
`_enter_degraded`, which releases NO further execution for the rest of the
process lifetime -- so ONE unexecutable decision stopped the entire bot, not
just that order. The raise read as a financial fail-closed, but the guard had
already decided this order's fate upstream: it is an AVAILABILITY hazard.

Root cause of reachability, found by the new test rather than by inspection:
the guard and the worker disagree on how to aggregate positions for a symbol.
`guard.py:80` builds `pos_map = {p["symbol"]: p for p in positions}` -- LAST row
wins -- while `worker.py:436-443` SUMS every row for the symbol. A broker
payload carrying two netting rows for one symbol (e.g. AAPL -10 then AAPL +10)
therefore lets the guard see qty=+10 with nothing in flight and APPROVE, while
the worker computes `10 - 10 = 0` and hit the raise. Negative `quantity`
(pending SELL larger than the position) reaches the same line.

Fix: skip THIS decision instead of raising -- same REJECTED write-back the
guard's rejection branch already uses (worker.py:426-431), a warning log line,
and `continue`. Fail-closed is preserved (nothing is submitted, the risk
decision is recorded REJECTED with a reason an operator can read) while the
blast radius drops from "whole worker, permanently" to "one row, next cycle
retries". No trading permission is widened: a later cycle re-derives the same
quantity and re-decides.

New tests (tests/test_worker_pending_sell_sizing.py, now 16 pure unit tests):
a two-netting-row payload that the guard approves and the worker computes as
0; a negative computed quantity; and a skip that does NOT stop the loop --
a second pending TSLA SELL still submits `quantity=5` in the same cycle. Each
asserts `executor.submissions` content, `worker.degraded is False`, and the
`sell_quantity_unavailable` reason on the write-back.

Validation: 16 new-file tests passed; guard/worker/daily-loss siblings 73
passed; ruff clean on both changed files; mypy clean on services/alpaca_paper.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health ok, open positions [AAPL, SPY, TSLA] (all ~0.01-0.03 fractional shares),
orders reported 0 vs actual 11, fills reported 0 vs actual 11, unrealized P&L
-0.008836 (equity 99951.33 / cash 99921.37), last_reconciled_at
2026-10-02T19:29:30Z. No new anomaly. The 0-vs-11 reported-count mismatch and
the per-order null `last_reconciled_at` both persist ONLY because the
agent-side fixes are not deployed to the frozen runtime (deploy requires human
approval).

### Cycle: guard/worker position aggregation mismatch (FIXED, recovery mode)

Started as RECOVERY MODE: dirty tree with a partially-finished uncommitted
change in `services/alpaca_paper/guard.py` (new `_net_positions` helper wired
into the per-symbol lookup) plus an untracked test file
`tests/test_guard_position_aggregation.py`. The premise was the FIRST candidate
task in the previous cycle's backlog.

Root cause: two components held two different numbers for the SAME position.
`guard.py` collapsed the broker's rows with `pos_map = {p["symbol"]: p ...}`
(LAST row wins) while `worker.py:436-443` SUMS every row for the symbol. Alpaca
normally returns one row per symbol so this was latent, but any multi-row payload
made the guard's verdict depend on the ORDER the broker happened to list rows in:

- rows `[+0.03, -0.02]` -> guard saw -0.02 -> SELL rejected as an illegal SHORT,
  stranding a genuinely long 0.01 position the worker would have closed;
- rows `[-0.02, +0.03]` -> guard saw +0.03 -> SELL approved on a magnitude the
  netted position (0.01) never justified.

Exposure had the mirror-image defect: the cap summed every row's `market_value`
GROSS, so a hedged pair counted 150 of exposure when the net was 15.

Fix: new `ExecutionGuard._net_positions` collapses rows into ONE netted entry
per symbol, summing `qty` and `market_value`, with `qty_known` /
`market_value_known` flags. One unsourceable leg makes the net UNKNOWN rather
than 0 -- inventing the missing leg would state a position the broker never
reported, so callers fail closed on it. Both consumers read the netted map: the
per-symbol lookup (pyramiding, SHORT check, dust check) and the BUY exposure cap.

Completed work this cycle: the WIP had wired netting into the lookup but left the
BUY exposure loop (guard.py:188-205) still summing per-row GROSS, so its own new
test `test_exposure_cap_uses_netted_market_value_per_symbol` failed on arrival.
Rewrote that loop to iterate the netted map; fail-closed semantics are unchanged
(an unsourceable qty or market_value on ANY leg still refuses the BUY), only the
aggregation is now netted.

Three tests in `tests/test_worker_pending_sell_sizing.py` (committed last cycle)
had to be rewritten. They reached the worker's `sell_quantity_unavailable` skip by
constructing the guard/worker DISAGREEMENT -- precisely the precondition this fix
eliminates. They now pin the stronger invariant: guard and worker agree, the guard
rejects the row itself, nothing is submitted, and the worker is NOT degraded.
`test_skipped_sell_does_not_block_later_pending_decisions` was renamed to
`test_netted_position_that_can_still_be_sized_is_submitted` and keeps its real
purpose (an unrelated TSLA SELL in the same cycle still executes).

Net effect: the root cause is now closed, not just the crash symptom the previous
cycle's skip-patch worked around. The worker's defensive skip remains in place as
belt-and-braces; the two components no longer disagree.

Validation: 6 new-file tests passed; guard/worker/daily-loss/executor sibling
suites 109 passed; ruff clean on all three changed files; mypy clean on
services/alpaca_paper/guard.py.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health ok, open positions [AAPL, SPY, TSLA] (all ~0.013-0.03 fractional shares),
orders reported 0 vs actual 11, fills reported 0 vs actual 11, unrealized P&L
0.048309 (equity 99951.39 / cash 99921.37, market_value 30.02), last_reconciled_at
2026-10-02T19:48:35Z. No new anomaly. Note the live open positions total
market_value 30.02, which is AT/ABOVE the `MAX_TOTAL_EXPOSURE` 30.00 cap, so new
BUYs are legitimately cap-blocked right now -- not a defect. The 0-vs-11
reported-count mismatch and the per-order null `last_reconciled_at` persist ONLY
because the agent-side fixes are not deployed to the frozen runtime (deploy
requires human approval).

### Cycle: notional order published as quantity=0 (FIXED, recovery mode)

Started this cycle with a dirty tree (broker route + its tests), so RECOVERY
MODE: no new task was chosen. The production change was already written and
correct; the TEST FIXTURE was not. `_order_row` still only accepted
`requested_at`, while the three new tests passed `requested_quantity=...` /
`filled_quantity=...` / `status=...`, so every one of them died with a
`TypeError` on the helper before reaching an assertion. The whole WIP was red
for a reason unrelated to the defect it was written to pin.

The defect: `get_broker_portfolio` mapped the response `quantity` from
`requested_quantity`, and `executor.py:151` deliberately stores that column as
NULL for a NOTIONAL order (`requested_quantity=quantity if notional is None
else None`) because a dollar-denominated BUY has no knowable share count until
the broker fills it. Coercing that NULL to `Decimal(0)` published a FILLED
trade beside `quantity: "0"` -- visible in the live snapshot, where three
FILLED notional BUYs (AAPL, SPY, TSLA) carry `"quantity": "0"` while the
positions they opened hold real fractional shares (0.0299 / 0.0129 / 0.0268).
The route now falls back to `filled_quantity` when `requested_quantity` is
NULL, and only then; a zero is published when it is true (an open notional
order with no fill genuinely traded nothing), never invented.

Recovery changes: extended `_order_row` with keyword-only
`requested_quantity` / `filled_quantity` / `status`, documented why NULL is a
legitimate fixture value, and left every default byte-compatible so the 18
pre-existing callers are unchanged.

Validated: 21 passed in tests/test_broker_portfolio_counts.py +
tests/test_health_paper_worker_ready.py (full file, not a subset), ruff clean,
mypy clean on the route. No production file was modified during recovery.

### Cycle: SELL local-side size coverage in `_assert_open_orders_known` (DONE, recovery mode)

Started as RECOVERY MODE: the tree was dirty with one uncommitted pure unit
test in tests/test_worker_reconcile_unknown_open_orders.py plus the matching
AGENT_LESSONS entry. No production code was in the WIP and none was needed.

The test pins the LOCAL-side NULL rule of the SELL branch
(worker.py:275-284): a local SELL row whose `requested_quantity` is NULL must
raise `broker_order_quantity_divergence`, not be read as "size zero matches".
I read the production branch before accepting the premise and confirmed it
already fails closed on `remote_quantity is None or local_quantity is None`,
symmetrically with the BUY branch (worker.py:265-274). So this was a genuine
COVERAGE HOLE, not a latent bug -- the one direction the family was missing.

`requested_quantity` is NULL for every NOTIONAL order (executor.py:151), and
every execution gate sizes a SELL from that column, so a NULL here is
"unknown", never "equal to anything". Worth keeping as a regression pin: the
`or 0`-style coercion that this repo already fixed in guard/worker/executor
would have silently opened this hole.

Validation: 18 tests in the file pass (full file); sibling guard/worker/daily-
loss suites 48 passed; ruff clean on the changed test; mypy clean on
worker.py (no production change -- `tests/` is outside the configured scope).

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health DEGRADED, last_reconciled_at 2026-10-02T20:22:37Z, open positions 3
(SPY/AAPL/TSLA, fractional, market_value 29.93), orders reported 0 vs actual
13, fills reported 0 vs actual 11, unrealized P&L -0.036279 (equity 99951.30 /
cash 99921.37), database up, market_data state market_closed.

Two anomalies, BOTH already root-caused and fixed on this branch and both
persisting ONLY because the frozen runtime is undeployed (deploy needs human
approval) -- neither is new work:

1. `/health` flaps: 15 of the last 25 samples report `health.status=degraded`
   while `paper.degraded=false` and `reconciled=true` every time, each taken
   0.5-8.8s after that sample's own `last_reconciled_at` -- i.e. inside the
   next reconcile cycle's fail-closed window. This is the exact
   `reconciliation_in_progress` sentinel misread as a fault, fixed by
   `AlpacaPaperWorker.health_ready()` in an earlier cycle. The sample cadence
   is now ~60s against a 3s reconcile, so the observer more often lands in a
   NON-cycle and the flap rate should fall once deployed.
2. Reported counts still 0 vs 13 orders / 0 vs 11 fills, and every
   `latest_orders[*].last_reconciled_at` is still null. Both agent-side fixes
   are committed but not deployed.

- `broker_order_quantity_divergence` (worker.py:284) now has pure unit coverage
  in BOTH directions (broker-side NULL and local-side NULL). The production
  branch was already correct; only the tests were asymmetric.
- `health.status=degraded` in `.agent-runtime/paper-observations.jsonl` with
  `paper.degraded=false` is the ALREADY-FIXED `health_ready()` bug, not a new
  fault. Do not re-investigate it. Diagnostic that distinguishes the two cases
  in one read: compare each sample's `observed_at` to that same sample's
  `paper.last_reconciled_at`. `health_ready()` only fails closed on
  `has_reconciled=False` or a REAL `degraded_reason`, so a `degraded` health
  paired with a healthy `paper` block and a small positive delta means the
  runtime is still running the pre-fix code.
- The `paper-latest.json` portfolio fields are FLAT (`paper.cash`,
  `paper.equity`, `paper.orders_count_reported`, ...), not nested under
  `paper.portfolio`. A first pass that looks for `paper.portfolio.orders`
  silently reads empty lists and reports orders/fills as 0 vs 0, which is
  indistinguishable from a real empty state. Dump the keys before trusting a
  zero.
- Per-order `latest_orders[*].last_reconciled_at` is null in the observation
  payload. The broker route now supplies it, so the null must come from the
  observation builder path -- see the next-task note in AGENT_STATE.md.

### Cycle: worker position-identity tripwire names WHICH cause (DONE)

- `_validate_positions` (services/alpaca_paper/worker.py:215) collapsed two
  DIFFERENT broker realities into the single reason
  `broker_position_identity_unknown`: a row whose symbol is missing or blank
  (unattributable) and a symbol the broker reported on more than one row
  (the position was split across rows). `degraded_reason` is the only string
  an operator gets, and the two causes have different remediations.
- The branches are now separate. Missing/blank symbol KEEPS
  `broker_position_identity_unknown` (unchanged, so existing log greps still
  match); a repeat symbol raises
  `broker_position_split_across_rows:{SYMBOL}`.
- NO safety semantics changed: both branches still raise, so a split payload
  still fails the cycle CLOSED into DEGRADED. Only the string an operator
  reads got sharper.
- Verified the split branch is genuinely reachable and not already netted
  away upstream: both call sites (worker.py:148 `reconcile_once`,
  worker.py:565 `_snapshot_broker_portfolio`) hand `_validate_positions` the
  RAW `adapter.get_positions()` rows. The per-symbol netting added in abe7d25
  lives DOWNSTREAM in `ExecutionGuard._net_positions`, and the snapshot write
  (`_save_broker_snapshot`, worker.py:556-560) still inserts one
  `broker_positions` row per broker row -- so a split payload really does have
  to fail closed here.
- New tests: tests/test_worker_position_identity_reasons.py (7 pure unit
  tests). It builds the worker with `AlpacaPaperWorker.__new__` to skip
  `__init__` -- safe because `_validate_positions` only reaches `_decimal`, a
  staticmethod, so no engine or broker is constructed. The split test pins the
  new reason AND asserts the unattributable string is ABSENT from it, so a
  future collapse back to one string fails the test.

Validation: 7 passed in the new file; 117 passed across the new file plus the
sibling guard/worker/daily-loss suites; 21 passed together with
tests/test_paper_v1_stabilization.py (the pre-existing direct caller); ruff
clean and mypy clean on worker.py. Grep confirms no other code, template or doc
references either reason string, so nothing else needed updating.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health.status=ok, last_reconciled_at 2026-10-02T20:34:49Z, open positions 3
(SPY/AAPL/TSLA fractional, market_value 29.92), orders reported 0 vs actual
13, fills reported 0 vs actual 11, unrealized P&L -0.053430 (equity 99951.29 /
cash 99921.37), database up, market_data state market_closed. The two
known-undeployed anomalies persist unchanged: every
`latest_orders[*].last_reconciled_at` is still null and the reported counts are
still 0 vs 13/11. Both fixes are committed but not deployed -- do not
re-investigate.

### Cycle: one bad reconciliation order no longer degrades the whole worker (FIXED, recovery mode)

- The worktree was DIRTY at cycle start (worker.py + an untracked test file),
  so this ran in RECOVERY MODE: no new task was chosen.
- `_reconcile_active_orders` (services/alpaca_paper/worker.py:568) looped over
  every active order calling `executor.reconcile_order` UNGUARDED.
  `AlpacaPaperExecutor._required_decimal` raises
  `RuntimeError("invalid_broker_<field>")` (executor.py:40,42) when a broker
  numeric cannot be sourced -- correct fail-closed, PER ORDER. But the raise
  escaped the loop, which meant ONE malformed payload for ONE order: (a) aborted
  reconciliation of every remaining order in the batch, leaving their fills
  unrecorded and in-flight exposure stale, and (b) reached `_run`
  (worker.py:125-127), whose `except Exception` calls `_enter_degraded`, which
  releases NO further execution for the REST OF THE PROCESS LIFETIME. That is an
  availability failure, not a fail-closed one.
- Fix: `except RuntimeError` scoped to the single `reconcile_order` call, a
  warning naming the order, then the loop continues. NO safety semantics
  weakened: the bad order still writes nothing (no fabricated 0), keeps its
  prior status so it stays in `ACTIVE_ORDER_STATUSES` and is RETRIED on a later
  cycle, and `reconcile_once` still owns `degraded`/`reconciliation_ready` -- the
  loop deliberately touches neither, so only a genuine whole-cycle failure
  degrades.
- Recovery work done on the WIP: the new test's `_worker(...)` fixture was
  RED (3 failures) because it built a worker via `AlpacaPaperWorker(...)` and
  asserted post-reconcile state, but `__init__` intentionally opens the worker
  fail-closed (`degraded=True`, `reconciliation_ready=False`,
  `degraded_reason="startup_reconciliation_pending"`) and only `reconcile_once`
  clears it -- which needs the adapter/DB the test deliberately avoids. Fixed
  the FIXTURE (set the post-reconcile state explicitly), NOT `__init__`.

Validation (re-run in the recovery cycle that committed it): 7 passed in
tests/test_worker_reconcile_isolates_bad_order.py; 99 passed across it plus the
sibling worker/executor/guard/pending-sizing/health suites; ruff clean on both
files; mypy clean (`services/alpaca_paper`, 6 files). No full suite run.

Scope check performed before committing: the only `RuntimeError` reachable from
`executor.reconcile_order` is `invalid_broker_<field>` (executor.py:40,42), so
the new `except RuntimeError` cannot swallow a safety invariant. The whole-cycle
divergences (`broker_order_*_divergence`, worker.py:265-293) raise from
`_assert_open_orders_known`, which is called by `reconcile_once`
(worker.py:150) -- OUTSIDE the loop -- so a payload-wide mismatch still degrades
the cycle, as it should.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health.status=degraded, equity 99951.29, orders reported 0 vs actual 13, fills
reported 0 vs actual 11, every `latest_orders[*].last_reconciled_at` still null.
Both remain the known-undeployed anomalies (fixes committed, frozen runtime not
rebuilt) -- do not re-investigate.

### Cycle: broker portfolio status derived from broker text (FIXED, recovery mode)

RECOVERY MODE: the cycle started with a dirty worktree holding an UNFINISHED
broker-route status fix. The production fix was correct and was kept; its only
test was DB-backed (unrunnable, Postgres down) and it had left the existing
pure-unit suite RED (9 failures, `KeyError: 'paper_status'`). Finishing that WIP
was the whole cycle -- no new task was chosen.

The defect: `get_broker_portfolio` set
`status=o["status"].upper() if o.get("status") else "UNKNOWN"`, re-deriving the
user-facing status from the RAW broker string instead of reading the mapped one.
`.upper()` is correct for exactly the ten states in
`AlpacaPaperExecutor._map_status`, but Alpaca also emits states OUTSIDE that map
(`done_for_day`, `halted`, `suspended`, `stopped`, `pending_replace`,
`calculated`, ...) and `.upper()` produced strings absent from the
`PaperOrder.status` Literal. Blast radius is TOTAL, not per-row: one unfamiliar
order status failed validation of the whole `PaperPortfolio` response model, so
an operator lost the ENTIRE endpoint -- positions, counts and all other orders.
Verified against pydantic directly: 7/7 of those strings are rejected.

Fix kept from the WIP: select `paper_orders.c.status.label("paper_status")` and
report `status=o["paper_status"]`, leaving the raw text verbatim in
`broker_status`. The label is load-bearing: the query selects the whole
`broker_orders` table, whose expansion already contains its own `status`, so an
unlabelled second `status` would silently resolve to the raw broker text again.
The local column is authoritative and safe to trust: `_map_status` already
mapped it, it is NOT NULL, and migration `863267844740` CHECK-constrains it
(`ck_paper_orders_state_m7`) to EXACTLY the contract Literal, degrading
unfamiliar broker text to UNKNOWN.

Recovery work added this cycle:

- Fixed the shared pure-unit fixture `_order_row` to model the observation
  builder honestly: `status` (raw broker text) and `paper_status` (mapped local
  value) are separate keys with separate defaults, deliberately NOT derived
  from one another, so a test can prove which source the route reports. The one
  caller that passed raw `status="NEW"` now passes `status="new"` +
  `paper_status="NEW"`.
- Added 3 executable tests (9 cases with the parametrization) in
  tests/test_broker_portfolio_counts.py: the status is the mapped value and not
  the uppercased broker string (asserting the two sources DISAGREE, so the test
  has teeth); 7 unfamiliar broker statuses each still return a full portfolio
  (positions + order + counts) instead of 500ing; and the projection still
  carries `paper_orders.status AS paper_status`.
- The DB-backed sibling in tests/test_broker_routes.py is KEPT as the real-schema
  proof; it now collects cleanly (3 tests) and will run when Postgres is up.
- Its 7 ruff findings all sit at lines 1-82; the diff only added lines 147-247,
  so the WIP introduced none (checked by line location, not by an out-of-tree
  HEAD copy -- see AGENT_LESSONS.md).

Continuation cycle (recovery mode again, same uncommitted work): re-validated
the above (19 passed, PYTEST_EXIT=0 unpiped; `--collect-only` 3 collected; ruff
locations all predate the diff), added the durable lesson, and COMMITTED. No new
task was chosen and no production code was changed in that continuation.

Validation: tests/test_broker_portfolio_counts.py 19 passed, PYTEST_EXIT=0
(unpiped -- a piped run reported exit 0 from `tail` and had masked the failure);
ruff clean on both changed files; the DB-backed file verified by
`--collect-only` only, since Postgres is down.

PAPER_REVIEW (read-only): status ACTIVE, paused=false, degraded=false,
reconciled=true, health.status=degraded, positions AAPL/SPY/TSLA,
cash 99921.37, equity 99951.30, market_value 29.93, orders reported/actual 0/0,
fills reported/actual 0/0, `latest_orders` len 10, all 10 with null
`last_reconciled_at`. All of it is the known-undeployed anomaly set -- do not
re-investigate.

### Cycle: simulator portfolio `mode` hardcoded to REPLAY (FIXED, recovery mode)

Started as RECOVERY MODE: dirty tree with an untracked WIP test
(`tests/test_paper_portfolio_mode.py`) pinning a defect in the SECOND
`PaperPortfolio` constructor. No production change was in the WIP, so the cycle
applied the fix and repaired the fixture.

The defect: `services/api/paper_queries.py:portfolio` read `status` and
`provider` off the `paper_runs` row but never `mode`, so the contract default
`"REPLAY"` (packages/contracts/paper.py:76) was published for every run. That
endpoint serves whichever run `system_controls.active_run_id` points at --
including an `ALPACA_PAPER` run, which is what this deployment runs -- so the
same money was labelled `"REPLAY"` here and `"ALPACA_PAPER"` by the sibling
broker route. `mode` is the one contract field that names the executor which
produced the numbers, and it was the one field that lied. Blast radius was the
whole payload, not a field.

Fix: `result.mode = run["mode"]` beside the existing `status`/`provider`
assignment. Read-only mapping change -- no schema change, no broker call, no
trading behavior.

Recovery work on the WIP (two fixture defects, not production defects):
- The test asserted lowercase `"alpaca_paper"`, but `ck_paper_run_mode` at
  migration head f2c8a51d9b10 is `mode IN ('REPLAY','ALPACA_PAPER')` -- UPPERCASE,
  and exactly the `PaperPortfolio.mode` Literal, so the column needs no
  translation. The lowercase value would have been rejected by pydantic.
- The stub connection's `_Mappings` had `.first()`/`.one()`/`.all()` but no
  `__iter__`; `portfolio` iterates `.mappings()` directly for the marks query,
  so 2 of the 3 tests died with `TypeError: '_Mappings' object is not iterable`
  before reaching the assertion they were written to prove.

Validation: 3 new-file tests passed; 36 passed with the broker-portfolio and
paper-v1-stabilization siblings; ruff clean on both changed files; mypy clean
on `services/api/paper_queries.py`. Confirmed pre-fix by `git show
HEAD:services/api/paper_queries.py` containing zero `result.mode` occurrences
(read-only dump to scratch, tree untouched).

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health.status=degraded, observed_at 2026-10-02T22:38:03Z,
last_reconciled_at 2026-10-02T22:37:55Z, open positions AAPL/SPY/TSLA
(0.0299 / 0.0130 / 0.0269 fractional, market_value 29.92), orders reported 0 vs
actual 13, fills reported 0 vs actual 11, unrealized P&L -0.047278 (equity
99951.29 / cash 99921.37), market_data state market_closed.

The reported-count mismatch, the per-order null `last_reconciled_at` (10 of 10)
and the `health.status=degraded` flap are all the KNOWN-UNDEPLOYED anomaly set
(fixes committed on this branch, frozen runtime not rebuilt) -- do not
re-investigate.

NEW observation, not previously recorded: `paper.mode` is `null` in the
observation payload even though `health.mode` is populated
("ALPACA PAPER — DINHEIRO VIRTUAL"). `services/alpaca_paper/observation.py` has
ZERO occurrences of `mode`, so the observation builder never populates it. Same
constructor-vs-contract-field class as this cycle's fix, one file over. See the
next-task note.

### Cycle: paper PAGE contracts could not name the live mode (FIXED, recovery mode)

Started as RECOVERY MODE: dirty tree carrying a production fix plus an untracked
WIP test (`tests/test_paper_page_mode.py`) for the paper PAGE contracts.

The defect: `PaperPositionsPage` / `PaperOrdersPage` / `PaperFillsPage` in
packages/contracts/paper.py declared `mode: Literal["REPLAY"]`, and
services/api/paper_routes.py built all three WITHOUT passing `mode`. The
contract default therefore published `"REPLAY"` for every page, and the
`Literal` could not even express `"ALPACA_PAPER"` -- which is what this
deployment runs. Same money, same run, three endpoints all claiming REPLAY
while the sibling portfolio route (fixed in the previous cycle) published the
run's real mode.

Fix: widen the Literal to `Literal["REPLAY", "ALPACA_PAPER"]` -- the exact
uppercase pair the `ck_paper_run_mode` CHECK constraint admits, so the contract
can no longer reject a mode the database permits -- and thread
`book.mode` from the already-read `PaperPortfolio` into each of the three page
constructors. Read-only mapping change: no schema change, no broker call, no
trading behavior.

Recovery work on the WIP (two fixture defects, NOT production defects):
- `PaperOrder.status` is a required contract field with NO default
  (packages/contracts/paper.py), and the `_order` fixture omitted it, so
  pydantic rejected every row before a single assertion ran. Added
  `status="FILLED"`.
- The stub built a FRESH `PaperPortfolio` on every `read_portfolio` call, each
  with a new `run_id`. The three route calls therefore served three different
  books, and the regression test comparing `page.run_id` to its own book could
  not pass for any implementation. The stub now builds ONE book at install
  time and serves it to every call. This is the same class of fixture bug
  recorded twice already this session (a stub that does not match the shape of
  the thing it stubs) -- third instance, and the one that actually masked the
  fix.

Validation: 3 new-file tests + 53 sibling tests (broker-portfolio-counts,
paper-stop, health) = 56 passed; ruff clean on all three touched files; mypy
clean on packages/contracts/paper.py and services/api/paper_routes.py. No
tracked production file was left temporarily broken: the WIP production fix
was already correct as found and was kept as-is.

PAPER_REVIEW: status ACTIVE, paused=false, degraded=false, reconciled=true,
health.status=ok (UP from the degraded flap last cycle), observed_at
2026-10-03T03:48:17Z, open positions AAPL / SPY / TSLA (TSLA avg 371.958 vs
370.590, market_value 9.953258, unrealized -0.036742), orders reported 0 vs
actual 13, fills reported 0 vs actual 11, equity 99951.30.

The reported-count mismatch and the per-order null `last_reconciled_at` are the
KNOWN-UNDEPLOYED anomaly set (fixes committed on this branch, frozen runtime
not rebuilt) -- do not re-investigate. `health.status` moving degraded -> ok on
its own is NOT a new finding.

### Cycle: `buying_power` NOT NULL contract pinned executably (DONE, recovery mode)

Started as RECOVERY MODE: dirty tree with a single untracked WIP test file,
`tests/test_broker_snapshot_not_null_contract.py`. No production change was
pending -- this cycle's whole job was to decide whether the WIP was worth
committing, and it was, so it was validated and committed.

The open candidate it closes: AGENT_STATE.md records a DELIBERATE decision that
`AlpacaPaperWorker._save_broker_snapshot` RAISES (`invalid_broker_buying_power`)
rather than writing NULL when the broker omits `buying_power`, precisely BECAUSE
`broker_portfolio_snapshots.buying_power` is NOT NULL. That decision was
previously only backed by a GREP plus prose, so the two sides of the contract
(model code and schema) could drift apart silently, in two directions:
relaxing the column and swapping `_decimal` for `_optional_decimal` would
re-introduce the exact `dict.get(key, 0)` fail-open class this worker's numerics
already got wrong once; keeping the raise but relaxing the column would make the
documented decision no longer describe the schema. Neither raises at the time it
lands.

The test pins all four sides: the write site must actually fill `buying_power`
(so the other two cannot pass vacuously), every column the write site fills must
be NOT NULL in the model metadata, `buying_power` must be NOT NULL in the model
metadata, the creating migration `db6f20ef0e19` must declare it
`nullable=False`, and no OTHER migration may touch `broker_portfolio_snapshots`
at head (a future `op.alter_column` could relax the column without editing the
file the other test reads). Pure unit tests: a stub engine records the real
insert without opening a connection, so no Postgres, no broker, no DB mutation,
no migration run.

Validation: 5 new tests pass; ruff clean on the file; mypy findings are the
`no-untyped-def` class that AGENT_LESSONS.md:749-757 records as pre-existing
convention for `tests/` (out of mypy's configured `files` scope) -- not a
regression. Non-vacuity was PROVEN, not assumed: a memory-only mutation setting
`c.buying_power.nullable = True` fails the two metadata tests, a temp-dir fake
later migration fails the "only author of this table" test, and rewriting the
creating migration's declaration to `nullable=True` fails the migration test
with its intended message. The write site fills all 8 table columns, so the
nullable-column check has no blind spot. Sibling run
`tests/test_worker_broker_numeric_fail_closed.py` stayed green; the 13
`tests/test_paper_audit.py` errors are the known environmental psycopg
ConnectionTimeout (see below), not from this WIP.

## Active blockers

None known at initialization.

## Known environmental test failures (do NOT re-investigate each cycle)

Postgres is not running in the agent environment, so DB-backed tests fail at
fixture setup. These are NOT caused by agent code changes:

- psycopg OperationalError / ConnectionTimeout (test_paper_audit,
  test_alpaca_paper_incident, many others)
- RuntimeError: alpaca_paper_startup_schema / `alpaca_paper_startup_refused_
  schema_not_at_head` raised at services/api/main.py:52 during the lifespan ->
  takes down tests/test_mission_control.py (3 tests: observation-worker
  factory + the two observation-loop cases, which then report "mock awaited 0
  times" as a cascade, not an independent defect)
- tests/test_alpaca_provider.py network smoke tests
- tests/test_replay_live.py: Windows FileNotFoundError (no ComSpec/SystemRoot)

Confirm any suspicious failure is DB/network at setup BEFORE blaming code.

## Next task

The three most recent cycles all ran in RECOVERY MODE and each closed and
committed one WIP: (1) the paper PAGE-mode contract
(`PaperPositionsPage`/`PaperOrdersPage`/`PaperFillsPage` now carry
`ALPACA_PAPER`, threaded from the portfolio's real `mode` in
services/api/paper_routes.py), (2) the `buying_power` NOT NULL contract test
(no production change), (3) the duplicate broker-order-claimed-on-one-local-row
guard in `_assert_open_orders_known` (see the cycle note below). The tree is
clean again, so the next cycle picks a candidate from the list below.

The `dict.get(key, 0)` broker-numeric audit is COMPLETE across all three
production layers (guard d55774e/6747abe, worker cc0acf5, executor this cycle).
Both branches of the worker's order builder are covered by pure unit tests
(SELL sizing 04b0f9f, BUY notional coverage, executor numerics).
The guard/worker POSITION AGGREGATION MISMATCH is fixed -- the guard now NETS
broker position rows per symbol (`ExecutionGuard._net_positions`) and both the
per-symbol lookup and the BUY exposure cap read that one definition.
The Paper-reported-counts observability defect is fixed (see cycle above).

Candidate next tasks (pick one in a clean cycle):

- OBSERVATION path null `last_reconciled_at` (confirmed FOUR times now in Paper):
  every `latest_orders[*]` entry in `.agent-runtime/paper-latest.json` carries
  `"last_reconciled_at": null` while the portfolio-level field is populated.
  The broker route now sets it, so find the SECOND constructor that builds the
  observation payload (services/alpaca_paper/observation.py or the Mission
  Control snapshot builder) and check whether it omits `last_reconciled_at` or
  reads it from the wrong table -- the same class as the route defect fixed in
  the last two cycles. Bounded: grep the `PaperOrder(`/`PaperPortfolio(`
  constructors in services/alpaca_paper/ and services/api/observation*.
- The 0-vs-7 `orders_count` observation defect is fixed on the BROKER route
  path (7252052) and, as of this cycle, so is the broker route's
  `requested_at` timestamp. The remaining agent-side gap is the SIMULATOR
  constructor: `services/api/paper_queries.py:28` builds a SECOND
  `PaperPortfolio` for the local/simulator path. Audit it for the same class of
  unset/wrong-field bug -- any contract field it leaves at its default (or
  fills with the wrong timestamp) while the broker route supplies it
  correctly. `grep PaperPortfolio(` finds exactly these two constructors, so
  this is a bounded two-file check. Note `paper_queries.py` reads
  `PaperOrder.model_validate(dict(r))` straight off `paper_orders`, so its
  `requested_at` is already correct by construction; the fields to scrutinize
  are the portfolio-level ones it hardcodes (cash/equity/market_value,
  counts, `reconciled`, `last_reconciled_at`).
- `broker_portfolio_snapshots.buying_power` NOT NULL assumption at migration
  head f2c8a51d9b10 -- NOW CLOSED. Verified and pinned executably by
  tests/test_broker_snapshot_not_null_contract.py (see the cycle note above):
  the creating migration still declares nullable=False, no other migration
  touches the table at head, and the worker's raise decision is now guarded
  against drift instead of resting on prose. Do NOT re-verify by grep; a
  violation now fails a test.
- `_process_pending_submits` raises `RuntimeError("sell_quantity_unavailable")`
  when computed qty <= 0 -- ALREADY FIXED (skip-the-row with a REJECTED
  write-back, see the cycle note above). Its RECONCILIATION twin had the same
  blast radius and is now fixed too: one bad `reconcile_order` no longer escapes
  the loop, so it can no longer degrade the whole worker. Both members of that
  fail-closed-vs-availability family are closed.
- Two broker open orders resolving to ONE local row in `_assert_open_orders_known`
  -- NOW CLOSED. The dicts now hold row INDEXES plus a `claimed` set, so a second
  claim raises `broker_open_order_duplicate_for_local_order:<id>`; the
  `index is None` (unknown) check still runs FIRST, so an unknown order is never
  misreported as a duplicate. Pinned by four tests including the positive
  control (two distinct rows must still reconcile) and the fail-closed ordering.
  Do NOT re-audit the mapping; a violation now fails a test.
- `broker_order_quantity_divergence` (worker.py:255) raises on quantity
  divergence and has no pure unit coverage; same fail-closed family, and it is
  reachable from the reconciliation path. STILL OPEN -- and note it is a
  WHOLE-CYCLE invariant, not a per-order outcome: the question worth asking is
  whether the raise is reachable per order (then it belongs inside the loop's
  guard) or only for a payload-wide mismatch (then degrading is correct).

## Cycle: recovery mode (worktree was dirty)

`git status` at cycle start showed one untracked file,
`tests/test_worker_unknown_order_aborts_whole_cycle.py`, with no matching
production change. So this was a RECOVERY cycle: finish and validate that WIP,
choose no new task. The file was a pure unit test pinning the OTHER half of the
blast-radius pair fixed in 8f31343 (`_reconcile_active_orders` isolates a bad
order per order; `_assert_open_orders_known` at worker.py:240 is deliberately
NOT wrapped and must abort the whole cycle, since its failure modes are
account-wide: an unknown live order, a terminal-status divergence, or a
symbol/side divergence all corrupt sizing for every remaining order, and
reaching `_save_broker_snapshot` would open `reconciliation_ready`/
`has_reconciled` on a disproven picture -- a fail-OPEN).

The WIP did not run. Two defects, both in the test, none in production code:

1. `_ScriptedAdapter.get_account` returned `{"status": "ACTIVE"}`. The control
   tests need a cycle that REACHES `_save_broker_snapshot`, and that writer
   reads cash/equity/portfolio_value/buying_power unconditionally and fails
   closed on a missing one -- so 3 tests died on `invalid_broker_cash` and were
   asserting the writer's failure instead of the assert's blast radius. Stub
   now returns all four fields.
2. `test_divergence_does_not_mark_the_picture_reconciled` asserted
   `has_reconciled is False` directly after the raise. That CONTRADICTS the
   durable-latch design: `reconcile_once` (worker.py:133-135) clears only the
   per-cycle bits, and `_enter_degraded` (worker.py:295-301) is what latches
   `has_reconciled = False`. A raise alone is not a signal -- `_run` decides
   what to do with it. Rewritten as
   `test_divergence_leaves_no_verified_picture_after_degrading`, which pins the
   real two-step path: mid-cycle state is fail-closed but still attributed to
   the in-progress sentinel, THEN `_enter_degraded` clears the latch and
   `health_ready()` goes False. The safety reason it now documents is the one
   from AGENT_LESSONS: without the durable latch the next cycle's
   "reconciliation_in_progress" sentinel self-heals a runtime failing every
   cycle.

Validation: 12 passed across the new file and its sibling
tests/test_worker_reconcile_isolates_bad_order.py; ruff clean. A broader
`-k "worker or health or reconcil"` selection was ABANDONED at 180s -- those
tests hit DB fixtures. Pre-existing/environmental, recorded here once rather
than rediscovered.

Note: `broker_order_quantity_divergence` (above) is now reachable from TWO pure
unit tests in the new file's family, so its remaining gap is the SELL-side
divergence, not the whole raise.

NOTE on the candidate below, updated this cycle: the SIMULATOR constructor
`services/api/paper_queries.py:portfolio` is now FIXED -- it publishes
`run["mode"]` instead of the contract's `"REPLAY"` default. That closes the
constructor-vs-contract-field audit for `PaperPortfolio.mode`. `PaperOrder`
there is still `PaperOrder.model_validate(dict(r))` straight off `paper_orders`,
so its `filled_quantity` is populated by the row, not the `Decimal(0)` default
-- already correct by construction, no work needed.

- `paper.mode` is `null` in `.agent-runtime/paper-latest.json` while
  `health.mode` is populated. `services/alpaca_paper/observation.py` contains
  ZERO occurrences of `mode`, so the observation builder never sets it. Bounded
  single-file audit: find the observation payload's own contract/dataclass and
  check whether it has a `mode` field that is never assigned, or whether the
  consumer (mission-control.html / the observation JSON schema) expects one.
  Same class as the last two cycles' `last_reconciled_at` null.
  TOP CANDIDATE: the last TWO cycles both found the same constructor-vs-field
  defect on the portfolio/page contracts, and this is the third and last
  constructor in that family. A `Literal` in the observation payload that
  admits only `REPLAY` would be the exact shape of the bug just fixed.
  Before editing, grep the observation contract for its `mode`/`status`
    Literals and compare them against `ck_paper_run_mode`'s two admitted values
    -- a Literal narrower than the CHECK constraint is the tell.
    CONFIRMED STILL OPEN this cycle: `'mode' in paper` is False on the live
    observation, so the field is genuinely absent from the payload, not null.
    The constructor audit is done; this observation-side gap is what remains.

To run tests, use the project venv python (see AGENT_LESSONS.md); the default
`python` on PATH has no pytest. The ambient shell exports DATABASE_ROLE=runtime
and EXECUTION_MODE=alpaca_paper, both of which conftest refuses -- prefix test
commands with `DATABASE_ROLE=test EXECUTION_MODE=local_paper`.

## Cycle: recovery mode -- duplicate broker order claimed on one local row

`git status` at cycle start showed two modified tracked files
(`services/alpaca_paper/worker.py`, `tests/test_worker_reconcile_unknown_open_orders.py`),
so this was RECOVERY MODE: no new task was chosen.

The WIP was coherent and complete, and it closes the order-side twin of a fault
already fixed for positions. `_assert_open_orders_known`
(services/alpaca_paper/worker.py:240, deliberately NOT wrapped -- see the
blast-radius lesson below) resolves each broker open order onto a local
`broker_orders JOIN paper_orders` row via `by_broker_id` then `by_client_id`.
It used to hold the ROWS in those dicts, so two DISTINCT broker orders could
resolve to the SAME row -- one matching on `broker_order_id`, the other on
`client_order_id` -- and each remote order then passed the symbol/side/size
checks on its own, so the batch reconciled "successfully". The exposure the bot
derives counts local ROWS (`_process_pending_submits` reuses them as the guard's
`in_flight`), so N live broker orders read as one: the order-side twin of
`_validate_positions`' `broker_position_split_across_rows`, which already
refuses the same shape for positions.

Fix: index the dicts (`row -> index`) instead of holding the rows, plus a
`claimed: set[int]`. A second claim of an already-claimed index raises
`broker_open_order_duplicate_for_local_order:<client_id or broker_id>`.
Fail-closed ordering is preserved: the `index is None` check still runs FIRST, so
an unknown order still reports `unknown_broker_open_order` rather than being
misreported as a duplicate.

Validation: 22 passed in tests/test_worker_reconcile_unknown_open_orders.py;
34 passed across that file plus its two sibling blast-radius files
(tests/test_worker_unknown_order_aborts_whole_cycle.py,
tests/test_worker_reconcile_isolates_bad_order.py); ruff clean.

Two defects were found in the WIP, both in the test file, none in production
code:

1. ruff E501 x2 (104 > 100) in the new control test's `_local_row(...)` calls.
   Wrapped the calls; ruff clean afterwards. The WIP had not been linted.
2. Non-vacuity was unproven, so it was proven WITHOUT editing tracked files
   (mission forbids restoring a known bug in-tree): a scratch replay of both
   resolution strategies on the duplicate shape printed
   `OLD: distinct rows matched = 2 raised = None` vs
   `NEW: distinct rows claimed = 1 raised = broker_open_order_duplicate_for_local_order`,
   plus the two-distinct-rows control `claimed = 2 raised = None`.
   `git show HEAD:services/alpaca_paper/worker.py | grep -c claimed` returns 0,
   confirming the guard is genuinely new.

The new tests also pin two things worth keeping: the two-row control (so the
guard cannot be "fixed" later by refusing all multi-order cycles) and the
fail-closed ordering (an unknown order is still reported as unknown).

PAPER_REVIEW (frozen runtime, read-only, this cycle):
  health.status=degraded, paper.status=ACTIVE, paused=false, degraded=false,
  reconciled=true, last_reconciled_at=2026-10-03T11:25:45Z, market_data
  state=market_closed. Open positions: AAPL, SPY, TSLA (all three micro-sized).
  orders_count_reported=0 vs orders_count_actual=13 (list len 10);
  fills_count_reported=0 vs fills_count_actual=11 (list len 10).
  unrealized_pnl=-0.0366820000, equity=99951.28, cash=99921.35,
  market_value=29.93.

Both reported-vs-actual mismatches and the `health.status=degraded` reading are
ALREADY-DIAGNOSED and expected on the frozen runtime, not new anomalies:

- `orders_count_reported=0` is the pre-fix behavior from the cycle that added
  `orders_count`/`fills_count` to `get_broker_portfolio`. The fix is committed
  here but the frozen runtime is undeployed (deploy needs human approval), so
  the observation keeps reporting 0. The `actual` values now grow (7 -> 13)
  precisely because the DB is being written to, which confirms the DB side of
  the run is healthy.
- `health.status=degraded` while `paper.degraded=false` is the `/health`
  execution-gate flap already diagnosed and fixed in a prior cycle; same
  undeployed-runtime cause. Confirmed in 14/41 then 15/25 samples previously.
- `latest_orders` list len 10 vs actual 13 is the documented `LIMIT 100` cap
  semantics, not a truncation bug at this scale.
- No broker/local divergence, no duplicate execution, no stale reconciliation,
  no accounting inconsistency in this sample.

Nothing here justifies overriding the backlog.

## Autonomous cycle incident (historical)

First autonomous cycle was interrupted before completion: investigation
expanded too far, a full-suite pytest baseline consumed excessive time, and
temporary experimental code was left in the worktree. It was discarded back to a
clean commit. The cycle size rules in AGENT_MISSION.md exist because of this.
The suspected daily-equity baseline issue it raised is now RESOLVED above.

## Cycle: recovery mode -- guard netting keyed on raw broker symbol casing

Cycle started with a dirty worktree (RECOVERY MODE, no new task chosen):
`services/alpaca_paper/guard.py` (+11) and `tests/test_alpaca_guard.py` (+61).

The WIP was coherent and complete. `ExecutionGuard._net_positions` keyed its map
on the RAW broker symbol while `evaluate` looks the position up under the
DECISION's symbol (`net_positions.get(symbol)`, guard.py:136). `PaperAlpacaWorker`
already upper-cases in BOTH `_validate_positions` (worker.py:218) and
`_save_broker_snapshot` (worker.py:542), and `_assert_open_orders_known`
compares with `.upper()` (worker.py:289) -- the guard was the only component
holding a raw broker string.

Silent in BOTH directions when the broker's casing disagreed:

- BUY: pyramiding is guarded by `if current_pos and current_qty > 0`, so a
  missed lookup SKIPS the check. The guard approved a second BUY on a symbol
  already held -- failing OPEN on the rule meant to prevent exactly that.
- SELL: the same None hit `if not current_pos` and refused to close a real
  held position, reporting "vendida a descoberto (SHORT)".

Fix (1 production line): normalise in the netting loop, `symbol = symbol.upper()`
(guard.py:62), so the map is built with one definition per position. Fixing the
lookup instead would have left the exposure sum iterating mixed-case keys.

Non-vacuity proven by scratch replay of HEAD vs worktree source (no tracked
file modified, mission-compliant):
  BUY  OLD: (True, None)   NEW: (False, 'Máximo 1 posição aberta por símbolo (no pyramiding)')
  SELL OLD: (False, 'Operação vendida a descoberto (SHORT) proibida na V1 (qty indisponível)')
       NEW: (True, None)
  mixed-case legs OLD keys ['AAPL','aapl'] qty 1/2 -> NEW keys ['AAPL'] qty 3 mv 30
  control, distinct symbols: NEW keys ['AAPL','SPY'] (no over-merge)
  control, uppercase-only: OLD and NEW maps and BUY verdicts identical

Validation: 35 passed across the five guard/decision test files; ruff clean on
`services/alpaca_paper/guard.py`; mypy clean on it. The 2 failures in
tests/test_alpaca_paper_incident.py are the known psycopg ConnectionTimeout
(Postgres down) -- the documented environmental class, not this WIP. The ruff
I001 on tests/test_alpaca_guard.py:1 is PRE-EXISTING at HEAD (reproduced on
`git show HEAD:tests/test_alpaca_guard.py`) and was deliberately left alone to
keep the diff to this task.

PAPER_REVIEW: no `.agent-runtime/` in this worktree (frozen runtime is a
separate worktree), so no observation was available this cycle. Nothing in the
runtime contradicts the committed work; the last recorded findings stand
(undeployed-fix reported-vs-actual mismatches, documented, not new anomalies).

## Cycle: recovery mode -- session analytics dropped SELLs with no BUY lot

Cycle started with a dirty worktree (RECOVERY MODE, no new task chosen):
`services/api/analytics.py` (+11) and the untracked
`tests/test_session_analytics_unmatched_sells.py` (160 lines). No
temporary/intentional breakage present; the WIP was coherent and needed only
validation, one lint fix and bookkeeping.

The WIP: `get_session_analytics` runs a per-symbol FIFO match over the run's
fills to build `closed_trades`/`pnl_realized`. A SELL whose BUY lot is not in
the same run (position opened in an earlier run, or a sell larger than this
run's buys) left a nonzero `sell_qty` after the `while` loop, which was then
discarded: no closed trade, no realized P&L, and no record that anything was
dropped. Reported session P&L under-stated reality with nothing in the payload
to explain the gap. The fix accumulates the leftover per symbol and reports it
as `anomalies.unmatched_sells`, deliberately WITHOUT inventing a cost basis,
so `pnl_realized` stays derived only from genuinely matched lots.

This is the analytics-side twin of the reconciliation class of defects fixed in
recent cycles (rows keyed on raw broker strings, two orders claiming one local
row): the local view cannot see a lot the broker knows about.

Two defects were found in the WIP, both in the test file, none in production:
1. ruff E501 x2 (102 and 105 > 100) on the stub connection's signature and one
   `_Result(...)` literal. Wrapped both; ruff clean afterwards.
2. Non-vacuity was unproven. Proven WITHOUT editing tracked files: a scratch
   harness loaded `git show HEAD:services/api/analytics.py` as a standalone
   module and ran both versions through the same stub scenarios --
   HEAD anomalies keys `['api_reconciliation_errors','dust_positions']`,
   WORK keys add `unmatched_sells`; sell-without-buy and partial-match report
   `[{symbol, quantity}]` while the fully-matched control reports `[]`;
   `git grep -c unmatched_sells HEAD` = 0 matches.

Validation: 6 passed in tests/test_session_analytics_unmatched_sells.py;
ruff clean on the new test file; ruff/mypy on analytics.py unchanged from HEAD
(13 ruff errors incl. I001/F401/E501 and 2 mypy var-annotated errors are all
PRE-EXISTING, reproduced on the HEAD blob in a scratch copy, deliberately left
alone to keep the diff to this task). tests/test_alpaca_deepseek.py also calls
`get_session_analytics` but needs Postgres (down) -- known environmental class.

PAPER_REVIEW (frozen runtime, read-only, this cycle):
  health.status=ok, health.database=up, paper.status=ACTIVE, paused=false,
  degraded=false, reconciled=true, last_reconciled_at=2026-10-03T13:12:19Z,
  market_data state=market_closed. Open positions: AAPL, SPY, TSLA (all three
  still micro-sized ~$10 each). orders_count_reported=0 vs actual=13;
  fills_count_reported=0 vs actual=11. unrealized_pnl=-0.0366820000,
  equity=99951.28, cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `ok`, not `degraded`. The execution-
gate flap noted in 14/41 then 15/25 samples did not reproduce in this sample,
consistent with the already-committed fix (still undeployed in the frozen
runtime) plus market_closed timing. The reported-vs-actual mismatches remain
the documented pre-fix reading of an undeployed runtime, not new anomalies; the
`_actual` values keep growing (13 orders / 11 fills), which is positive
evidence the DB side of the run is healthy. No broker/local divergence, no
duplicate execution, no stale reconciliation, no accounting inconsistency.

Nothing here justifies overriding the backlog.

## Cycle: recovery mode -- finish the SELL-size blast-radius test

Cycle started dirty (RECOVERY MODE, no new task chosen): one modified file,
`tests/test_worker_unknown_order_aborts_whole_cycle.py` (+69), adding
`test_sell_quantity_divergence_aborts_the_cycle_despite_healthy_siblings`. No
production code in the WIP, so there was no temporary breakage to revert.

The WIP was coherent and right about the production contract: a SELL whose
broker `qty` differs from the approved `requested_quantity` raises
`broker_order_quantity_divergence` out of `_assert_open_orders_known`
(worker.py:150), which is unwrapped on purpose, so the cycle aborts before
`_save_broker_snapshot` even though two of the three open orders verify
cleanly. Only the assertions were wrong: the WIP asserted
`worker.has_reconciled is False` and `health_ready() is False` straight after
`reconcile_once()` raised, i.e. 1 failed, 5 passed.

Root cause of the failure: `reconcile_once` deliberately clears only the
per-cycle bits; the DURABLE latch `has_reconciled` is cleared solely by
`_enter_degraded`, the handler `_run` wraps the call in. `health_ready()`
additionally excuses the `reconciliation_in_progress` sentinel, so it stays
True right after a raise. That split is already pinned by
`test_divergence_leaves_no_verified_picture_after_degrading`; the WIP had
duplicated the latch assertion into a test that never reaches the handler, so it
asserted a behaviour the design forbids. Fixed in the TEST, not the worker:
assert the mid-cycle state (`reconciliation_ready` False, `degraded` True,
`degraded_reason == "reconciliation_in_progress"`), then call
`_enter_degraded("broker_order_quantity_divergence:b-3")` before asserting
`has_reconciled is False` and `health_ready() is False`.

Non-vacuity proven WITHOUT editing any tracked file: a scratch test outside the
repo monkeypatched `_assert_open_orders_known` at runtime to neutralise only the
SELL size comparison (rewriting each remote `qty` to the approved 10) and reran
the identical three-order scenario. Result: `snapshot_writes=1, gate=True,
has_reconciled=True` -- without the size check the divergent book is
snapshotted and the execution gate OPENS. So the committed abort is doing real
work. Scratch file deleted; `git status` shows only the intended change.

Validation: 35 passed across tests/test_worker_unknown_order_aborts_whole_cycle.py,
tests/test_worker_reconcile_unknown_open_orders.py and
tests/test_worker_reconcile_isolates_bad_order.py; ruff clean on the modified
test file. No production file touched, so no production lint/type delta. The
known psycopg ConnectionTimeout failures in the Postgres-dependent test files
remain the documented environmental class.

PAPER_REVIEW (frozen runtime, read-only, this cycle):
  health.status=degraded, health.database=up, market_data state=market_closed,
  paper.status=ACTIVE, paused=false, paper.degraded=false, reconciled=true,
  last_reconciled_at=2026-10-03T13:29:23Z. Open positions AAPL, SPY, TSLA, all
  still micro-sized ~$10 each. orders_count_reported=0 vs actual=13;
  fills_count_reported=0 vs actual=11. unrealized_pnl=-0.0366820000,
  equity=99951.28, cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is back to `degraded` (it was `ok`), which
is the execution-gate flap recorded in earlier cycles -- the frozen runtime does
not have the committed `health_ready()` fix deployed. The sample was taken
13:29:27Z, ~4s after a successful reconcile at 13:29:23Z, i.e. inside the next
cycle's 3s fail-closed window, which is exactly the shape that fix addresses.
`paper.degraded` is false and reconciliation is current, so this is the known
in-progress-window flap, not a proven fault. Reported-vs-actual counts are the
same documented undeployed pre-fix reading; `_actual` still 13/11, and the two
newest orders are the expected intraday SELL pair, no duplicate execution, no
broker/local divergence, no accounting inconsistency. Nothing here justifies
overriding the backlog.

Next candidate task: the reported-vs-actual mismatch is fixed in the committed
code but still visible in the frozen runtime, so what remains there is
deployment, not code. Next code task worth taking on a clean cycle:
`get_session_analytics` reports `anomalies.unmatched_sells` as a bare
`[{symbol, quantity}]` list -- give it the same treatment the other anomaly keys
already get (a counted, attributed summary) so the paper pages can show it
without parsing a raw list, with a test pinning the count.

================================================================================
CYCLE 2026-10-03 (worktree clean -> new task)

TASK: `get_session_analytics` could never report a non-zero session return.

The `equity_initial` and `equity_final` figures were BOTH read from
`broker_portfolio_snapshots`, but that table is not a time series. `provider` is
its primary key (services/api/models.py:226) and the worker maintains it with
`insert(...).values(provider="alpaca", ...)` +
`on_conflict_do_update(index_elements=["provider"])` (services/alpaca_paper/worker.py:564),
so it holds exactly ONE row per provider carrying CURRENT broker state. The two
reads were therefore returning the same value: `equity_initial == equity_final`
on every session, and `return_pct` divided by the current equity instead of the
session's starting cash. The old code even asked for the OLDEST row
(`ORDER BY last_reconciled_at ASC LIMIT 1`), an ordering that cannot help when
only one row exists.

CHANGES (1 production file, 1 new test file):
- services/api/analytics.py: dropped the `snap_first` query entirely and take the
  opener from `run_row["initial_cash"]`, the run's own starting cash, which is
  `nullable=False` in models.py. The live snapshot is still read once for
  `equity_final`, and the no-snapshot fallback to starting cash is preserved. This
  also makes the code match the documented contract in docs/M4_CORE.md:67,
  `return_pct = (equity final - initial cash) / initial cash * 100`.
- tests/test_session_analytics_equity_initial.py (new, 4 tests): opener is the
  run's starting cash and not the live equity; a +20 round trip on 1000 of
  starting cash returns 2.0% and explicitly NOT the old 20/1042.5; a control that
  `equity_final` still tracks the live snapshot; and the pre-first-reconcile
  fallback where both ends equal the starting cash.

VALIDATION: RED first -- 3 of the 4 new tests failed on the unfixed code
(`assert '1042.5' != '1042.5'`, and `assert 1.9184652278177459 == 2.0` showing
the live-equity denominator), with only the fallback test passing. GREEN after
the fix: 10 passed across the new file and
tests/test_session_analytics_unmatched_sells.py. Lint baseline proven rather
than assumed: `git show HEAD:services/api/analytics.py` carries 13 ruff errors
and the same 2 mypy `var-annotated` errors (`fifo_buys`, `rejections`), while the
edited file carries 11 ruff errors and the identical 2 mypy errors -- so this
cycle REMOVED 2 pre-existing lint findings and added none. The file was
deliberately not reformatted (that would be a drive-by refactor of a
pre-existing violation).

Two unrelated pre-existing failures surfaced in a broader keyword slice and were
confirmed NOT mine: tests/test_alpaca_provider.py::
test_opted_in_smoke_closed_session_is_bounded_and_skips_stream fails on
`<module 'scripts.smoke_test'> has no attribute 'Settings'`, and
tests/test_alpaca_deepseek.py::test_analytics_run_isolation_and_realized_pnl
errors on a SQLAlchemy DB connection (the documented environmental class).
Neither reaches the analytics payload.

PAPER_REVIEW (frozen runtime, read-only, this cycle):
  health.status=degraded, paper.status=ACTIVE, paused=false, degraded=false,
  reconciled=true, last_reconciled_at=2026-10-03T13:36:25Z, market_data
  state=market_closed. Open positions AAPL, SPY, TSLA, all micro-sized ~$10.
  orders_count_reported=0 vs actual=13 (list len 10); fills_count_reported=0 vs
  actual=11 (list len 10). unrealized_pnl=-0.0366820000, equity=99951.28,
  cash=99921.35, market_value=29.93.

Same shape and same totals as the previous cycle, so this is the already
documented undeployed pre-fix reading, not a new anomaly: the counted-report
fix is committed but the frozen runtime predates it, and `health.status=degraded`
is the known execution-gate flap. `_actual` unchanged at 13/11. Nothing here
justifies overriding the backlog.

Next candidate task: `return_pct` now uses the correct denominator but still
numerates from `total_pnl` (realized + unrealized), while docs/M4_CORE.md:67
defines it as `(equity final - initial cash) / initial cash * 100`. The two
disagree whenever cash moved for a reason other than PnL (fees settling, a
deposit, an unpriced dust lot). Reconcile the code to the documented formula,
with a test that pins a session whose cash and PnL diverge.

================================================================================
CYCLE 2026-10-03 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The cycle started with a dirty tree
(`M AGENT_STATE.md`, `M services/api/analytics.py`,
`?? tests/test_session_analytics_equity_initial.py`), so per the mission's
dirty-worktree rule this cycle only reviewed, re-validated and committed the
previous cycle's unfinished work: `get_session_analytics` could never report a
non-zero session return because `equity_initial` and `equity_final` were BOTH
read from `broker_portfolio_snapshots`, a single-row-per-provider upsert table
(`provider` is the PK, models.py:226; worker.py:564 uses
`on_conflict_do_update`). The removed query even asked for the oldest row, an
ordering that cannot mean anything when only one row exists.

REVIEW OF THE WIP: no temporary or intentionally-broken code present. The fix
takes the opener from `run_row["initial_cash"]` (NOT NULL in models.py, with
`ck_paper_run_money` requiring `> 0`), keeps the live snapshot for `equity_final`
and preserves the no-snapshot fallback. The new test drives
`get_session_analytics` against a stub connection, so no Postgres is needed.

VALIDATION (re-run independently this cycle, not taken on trust):
- 10 passed in 0.07s across tests/test_session_analytics_equity_initial.py and
  tests/test_session_analytics_unmatched_sells.py.
- Lint baseline re-proven by feeding HEAD's file to ruff on stdin:
  `git show HEAD:services/api/analytics.py | ruff check --stdin-filename
  services/api/analytics.py -` -> 13 errors; the worktree file -> 11. The change
  removed 2 pre-existing findings and added none.
- mypy on the file: the same 2 pre-existing `var-annotated` errors
  (`fifo_buys`:58, `rejections`:150), both untouched by this diff.

PAPER_REVIEW: degraded/no-new-actionable-finding
  Read-only from the frozen runtime, observed_at=2026-10-03T13:52:37Z.
  health.status=degraded, health.database=up, market_data state=market_closed,
  paper.status=ACTIVE, paused=false, paper.degraded=false, reconciled=true,
  last_reconciled_at=2026-10-03T13:52:30Z. Open position symbols AAPL, SPY,
  TSLA, all still micro-sized ~$10 each. orders_count_reported=0 vs
  orders_count_actual=13; fills_count_reported=0 vs fills_count_actual=11.
  unrealized_pnl=-0.0366820000, equity=99951.28, cash=99921.35,
  market_value=29.93.

Same shape and same totals as the two previous cycles, so this remains the
already documented undeployed pre-fix reading rather than a new anomaly: the
counted-report fix is committed but the frozen runtime predates it, and
`health.status=degraded` is the known execution-gate flap. The newest pair is
the expected intraday SELL of the AAPL and TSLA micro-lots -- no duplicate
execution, no broker/local divergence, no accounting inconsistency. Nothing here
overrides the backlog.

Next candidate task (unchanged, carried forward): reconcile `return_pct` with
docs/M4_CORE.md:67 -- it still numerates from `total_pnl` instead of
`equity_final - initial_cash`.

================================================================================
CYCLE 2026-10-03 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The tree was dirty (`M services/api/analytics.py`,
`M tests/test_session_analytics_equity_initial.py`,
`?? tests/test_session_analytics_return_pct.py`), so this cycle only reviewed,
validated and committed the previous cycle's unfinished work -- exactly the
"next candidate task" recorded at the end of the prior state file: reconcile
`return_pct` with the formula in docs/M4_CORE.md:67.

REVIEW OF THE WIP: no temporary or intentionally-broken code present; the change
is confined to the numerator of one metric and its tests. `total_pnl` (this run's
matched FIFO realized P&L + the unrealized P&L of the CURRENT position book) was
being reported as `return_pct`, which is a different quantity from the change in
the ACCOUNT. The fix numerates from `equity_final - initial_cash`, i.e. exactly
what docs/M4_CORE.md:67 documents. This is the second half of the same defect the
previous cycle fixed on the denominator: the opener was the live equity, and now
the numerator is a P&L figure the account never agreed to.

Why the old numerator was wrong, concretely (each case is now a test):
- an unmatched SELL has no local BUY lot, so its P&L is deliberately NOT realized
  (it surfaces as `anomalies.unmatched_sells`), and the account's actual loss
  vanished from `return_pct`;
- a lot inherited from an earlier run that opens or closes inside this session
  moves the account with no local fill walk to explain it;
- fees settling, a deposit, or a dust lot can move cash in either direction;
- worst case, a real loss on one symbol netted against an unrelated gain on
  another and reported a healthy session.

CHANGES were already made by the interrupted cycle; this cycle verified them and
adjusted ONE test: `test_return_pct_is_measured_against_the_starting_cash` in
tests/test_session_analytics_equity_initial.py had been written to pin the
DENOMINATOR using the default SNAPSHOT_EQUITY of 1042.5, which under the new
numerator makes the account and the P&L disagree, so it now pins the snapshot
equity to 1020 (initial cash plus exactly the +20 realized) and delegates the
disagreement case to the new file. No production file was changed this cycle.

VALIDATION (re-run independently, not taken on trust):
- 15 passed in 0.11s across tests/test_session_analytics_return_pct.py,
  tests/test_session_analytics_equity_initial.py and
  tests/test_session_analytics_unmatched_sells.py. A keyword slice
  (`-k "session_analytics or analytics"`) gives the same 15 passed plus one
  ERROR, tests/test_alpaca_deepseek.py::
  test_analytics_run_isolation_and_realized_pnl, on
  `psycopg.errors.ConnectionTimeout` -- the documented environmental class
  (Postgres is not running here).
- Non-vacuity proven WITHOUT editing any tracked file: a scratch harness loaded
  `git show HEAD:services/api/analytics.py` as a standalone module and ran the
  new test file's scenarios against it. 3 of the 5 fail on HEAD (the P&L-vs-equity
  case, the unmatched-SELL case and the inherited-lot case); the 2 that pass are
  the deliberate CONTROLS where equity and P&L agree, so the fix cannot be read
  as "always report the equity". Scratch file deleted.
- Lint/type baseline: `ruff check` reports the identical 11 pre-existing errors on
  the worktree file and on the HEAD blob (9 E501, 1 F401, 1 I001 -- no delta);
  mypy reports the same 2 pre-existing `var-annotated` errors (`fifo_buys`:58,
  `rejections`:160). ruff clean on both test files.
- Consumer check: the only production consumer of `return_pct`
  (`services/api/observer_source.py:156`) reads it from the ACCEPTED BACKTEST
  report's metrics, a different payload produced by services/backtesting, so no
  downstream contract is touched by this change.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-03T14:12:43Z): health.status=ok, health.database=up, paper.status=ACTIVE,
paused=false, paper.degraded=false, reconciled=true,
last_reconciled_at=2026-10-03T14:12:42Z. Open position symbols AAPL, SPY, TSLA,
all still micro-sized (SPY $9.99, TSLA $9.95; AAPL likewise ~$10).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `ok` again (it was `degraded` in the
three previous samples) -- the known execution-gate flap, not a new fault. Totals
are unchanged (13 orders / 11 fills, same equity and P&L), so this is still the
documented undeployed pre-fix reading rather than new drift: the counted-report
fix is committed but the frozen runtime predates it. Every
`latest_orders[*].last_reconciled_at` is STILL null while the portfolio-level
field is populated, i.e. that long-standing candidate task remains open. The
two newest orders are the expected intraday SELL pair for the AAPL and TSLA
micro-lots. No broker/local divergence, no duplicate execution, no stale
reconciliation, no accounting inconsistency. Nothing here justifies overriding
the backlog.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in FIVE consecutive Paper samples -- every
`latest_orders[*]` entry carries `"last_reconciled_at": null` while the
portfolio-level field is populated. The broker route now sets it, so the SECOND
constructor of the observation payload is the suspect: grep the `PaperOrder(` /
`PaperPortfolio(` constructors in services/alpaca_paper/ and services/api/
(paper_routes.py already supplies it correctly; services/api/paper_queries.py:28
builds the second `PaperPortfolio` for the simulator path).

================================================================================
CYCLE 2026-10-04 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The tree was dirty (`M services/api/broker_routes.py`,
`M tests/test_broker_portfolio_counts.py`), so per the recovery rule this cycle
only reviewed, validated and committed that unfinished work.

REVIEW OF THE WIP: no temporary or intentionally-broken code present. The change
is one constructor argument plus three focused tests. `PaperPortfolio.reconciled`
defaults to `True` (packages/contracts/paper.py:106) and the broker route never
passed it, while it DID derive `degraded` from the snapshot status. So a snapshot
latched DEGRADED/STALE -- i.e. the last reconciliation cycle FAILED and the
positions may not match the broker -- was published as
`"reconciled": true, "degraded": true`. Both flags describe the same stored
latch, so the fix derives both from it (`reconciled = not degraded`), which makes
disagreement structurally impossible rather than merely fixed today.

CHANGES (already made by the interrupted cycle; verified, not rewritten):
- services/api/broker_routes.py: one hoisted `degraded` local used for both
  `degraded=` and the newly supplied `reconciled=`.
- tests/test_broker_portfolio_counts.py: `_StubConnection` takes a per-case
  `snapshot_status` so the latch can be driven; three tests added -- the two
  failure statuses must never publish reconciled, the ACTIVE CONTROL must still
  publish True, and the two flags are always opposed for every status.

VALIDATION (re-run independently, not taken on trust):
- 25 passed in 0.38s for tests/test_broker_portfolio_counts.py; the 9 tests
  selected by `-k "reconcil or degraded"` pass.
- `ruff check` clean on both changed files; `mypy services/api/broker_routes.py`
  clean (no issues in 1 source file).
- Non-vacuity proven WITHOUT editing any tracked file:
  `git show HEAD:services/api/broker_routes.py | grep -n reconciled` returns only
  `last_reconciled_at` hits and no `reconciled=` kwarg, which is direct evidence
  the field was never supplied on HEAD and therefore defaulted to True. Read-only;
  no bug restore was performed.
- Latch reachability checked so the inversion cannot be fooled by a third value:
  `broker_portfolio_snapshots.status` is only ever written `ACTIVE`
  (worker.py:151 `reconcile_once`, worker.py:587 `_snapshot_broker_portfolio`) or
  `DEGRADED` (worker.py:329 `_enter_degraded`). `STALE` is in the membership test
  defensively and is never written.
- Consumer check: grep for `.reconciled` / `reconciled=` across services/ finds
  only this route; no production consumer branches on the field, so the change
  has no downstream contract effect. tests/test_broker_routes.py inserts
  `status="ACTIVE"` snapshots, so its expectations are unchanged.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-04T01:49:48Z): health.status=degraded, health.database=up,
market_data.state=market_closed, paper.status=ACTIVE, paused=false,
paper.degraded=false, reconciled=true, last_reconciled_at=2026-10-04T01:49:45Z.
Open position symbols AAPL, SPY, TSLA, all still micro-sized (~$9.95-9.99 each).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `degraded` again (it was `ok` last
cycle) -- the known execution-gate flap documented in prior cycles, not a new
fault. Equity, P&L and both totals are IDENTICAL to last cycle, so this is still
the documented undeployed pre-fix reading rather than new drift: the counted-
report fix is committed but the frozen runtime predates it. Two new orders are
the expected intraday SELL pair for the AAPL and TSLA micro-lots (both
ACCEPTED, filled_quantity 0E-10, so not yet filled). No broker/local
divergence, no duplicate execution, no stale reconciliation, no accounting
inconsistency. Every `latest_orders[*].last_reconciled_at` is STILL null while
the portfolio-level field is populated -- the long-standing candidate task
remains open and is still the one to take next.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in SIX consecutive Paper samples -- every
`latest_orders[*]` entry carries `"last_reconciled_at": null` while the
portfolio-level field is populated. The broker route supplies it, so the SECOND
constructor of the observation payload is the suspect: grep the `PaperOrder(` /
`PaperPortfolio(` constructors in services/alpaca_paper/ and services/api/
(paper_routes.py already supplies it correctly; services/api/paper_queries.py:28
builds the second `PaperPortfolio` for the simulator path).
