# TradingBot Agent Lessons

Durable engineering memory for autonomous development.

## One definition per concept (guard/worker position aggregation)

A latent multi-row defect lived for several cycles because the broker NORMALLY
returns one position row per symbol, and both components' tests were pure unit
tests that always passed exactly one row per symbol. The trap:

- `ExecutionGuard` collapsed rows with `pos_map = {p["symbol"]: p for p in positions}`
  (LAST row wins), so its verdict depended on the ORDER the broker listed rows in;
- `PaperAlpacaWorker._process_pending_submits` SUMmed every row for the symbol.

Same position, two different numbers, in either direction of harm. The symptom
that finally exposed it was an availability one, not a correctness assertion: the
guard approved a SELL the worker then computed as 0 and raised
`sell_quantity_unavailable`, degrading the entire worker for the process lifetime.
A previous cycle patched the SYMPTOM (skip the decision); the root cause took
another cycle because the tests that motivated it were asserting the symptom's
reachability.

Reusable rules:

- When two components consume the same broker payload, grep for how EACH
  aggregates it. One sum and one last-wins in the same codebase is a latent
  divergence, not a style difference.
- For a fail-closed numeric aggregate, carry a `*_known` flag rather than
  defaulting the missing leg to 0. Summing with an invented 0 states a position
  the broker never reported. `ExecutionGuard._net_positions` returns
  `{symbol: {qty, market_value, qty_known, market_value_known}}`; one
  unsourceable leg makes the whole net UNKNOWN and callers fail closed.
- The netted map must be the single input to EVERY consumer of the payload, not
  just the one that triggered the bug. The WIP that introduced `_net_positions`
  rewired the per-symbol lookup but left the BUY exposure cap summing per-row
  GROSS `market_value` -- its own new test caught it on arrival. When a fix
  introduces a shared derived value, enumerate the consumers before committing.
- Fixing a root cause can invalidate tests that PROVED the old symptom was
  reachable. Rewrite them to pin the stronger invariant (the two components
  agree) rather than deleting them, and say in the commit/state why.

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

## Fail-closed reasons must name the failing side

The daily-loss breaker has TWO independent unsourceable inputs: the baseline
(`last_equity`) and the current `equity`. Both returned the identical string
"Equity indisponível para checagem do Daily Breaker", so an operator could not
tell them apart in `risk_decisions.reason` or in the guard's log line, even
though the remediations differ (a broker account payload missing `last_equity`
vs a payload missing `equity`).

Lesson: when two distinct degraded-data conditions share one rejection reason,
the reason is operationally useless -- fail closed is not the same as
diagnosable. Distinguish the conditions in the message.

Convention adopted: keep a shared stable prefix and append the failing side.

- "Equity indisponível para checagem do Daily Breaker (baseline last_equity
  ausente ou inválido)"
- "Equity indisponível para checagem do Daily Breaker (equity atual ausente ou
  inválido no snapshot da corretora)"

The shared prefix matters: existing tests and log greps match on
"Equity indisponível", and the genuine `Circuit breaker diário` message must
stay distinguishable from a data-availability failure. Baseline is checked
first so a fully-unavailable account produces a stable reason.

Safety semantics were NOT changed by this: both paths still fail CLOSED on BUY
and SELL is still unaffected. Tests:
tests/test_daily_loss_breaker_reason_observability.py.

## Worker broker-numeric accounting fail-closed (FIXED) -- audit now CLOSED

Fourth and final instance of the `dict.get(key, 0)` bug class, in the worker's
own accounting (the guard's instances are above). Same trap, one level
deeper: `AlpacaPaperWorker._decimal` DID raise on an unsourceable value, but
the call sites passed a `, 0` DEFAULT INTO it. `dict.get("k", 0)` returns an
INVENTED 0 for a missing key, so `_decimal` succeeded on a value that never
existed. A strict parser does not help if the caller pre-fabricates the input.

Sites fixed (all now pass raw `dict.get(key)`):

- `pending_sell_quantity` in `_process_pending_submits` (worker.py:414) -- a
  pending SELL row with NULL quantity summed as 0 sold, overstating
  `available_qty`. Defense-in-depth only: `ExecutionGuard.evaluate` already
  fails closed on an unsourceable in-flight SELL quantity BEFORE this line.
- `buying_power` and `unrealized_pl` in `_save_broker_snapshot`
  (worker.py:451, :458) -- these feed ONLY the `broker_portfolio_snapshots`
  observability row, so an absent field wrote a plausible-looking 0 and
  Mission Control showed a real-looking ACTIVE account with no buying power
  and zero unrealized P/L. Wrong numbers presented as authoritative.

Lessons:

- `dict.get(key, default)` is a silent fail-open even when the value is fed to
  a strict validator. When the default is passed INTO a parsing helper, the
  helper can never see the absence. Pass the raw `.get(key)` and let the
  helper decide.
- Parsing BEFORE opening an engine connection makes these paths unit-testable
  with a stub engine: `_save_broker_snapshot` raises `invalid_broker_<field>`
  on every field before `self.engine.begin()`, so no DB is needed to prove a
  fabricated zero never reaches the snapshot row (asserted by
  `test_fail_closed_occurs_before_any_write`).
- An observability column that is NOT NULL forces a deliberate choice: raise,
  or allow NULL plus a migration. Chosen here: RAISE. It needs no schema
  change, matches the three sibling account fields (`cash`, `equity`,
  `portfolio_value`) which already raised, and keeps the row's real-vs-absent
  status visible by absence rather than by a NULL that looks like a real
  balance of zero.
- Fail-closed here is DEGRADED, not permissive: `_run` (worker.py:97-99)
  catches the `invalid_broker_*` RuntimeError and calls `_enter_degraded`,
  which marks the snapshot DEGRADED in the DB. A payload too poor to account
  for is not allowed to publish an invented balance.

Tests: tests/test_worker_broker_numeric_fail_closed.py (7 pure unit tests, no
Postgres/broker/DB mutation). The `dict.get(key, 0)` audit is now CLOSED across
both guard and worker; the convention going forward is: every broker numeric
reaches `_decimal`/`_optional_decimal` RAW, with no `, 0` default anywhere.

## Executor fail-closed on required broker numerics (FIXED) -- audit CLOSED

Final production layer of the `dict.get(key, default)` bug class, and the most
damaging instance. `reconcile_order` used
`Decimal(str(remote_order.get("filled_qty", "0")))` and then gates fill
persistence on `if filled_qty > 0 and actual_broker_id`. A fabricated 0 therefore
skipped the whole `get_fills` block: real fills were NEVER written to
`broker_fills` while the order rows still showed the broker's status. The local
ledger silently under-reported execution -- the failure mode matters more here
than in the guard/worker instances because nothing else would reveal it.

Fixed with `AlpacaPaperExecutor._required_decimal`, which raises
`RuntimeError("invalid_broker_<field>")` on absent, None, empty, unparsable or
non-finite input. Four call sites: `filled_qty` in both
`_handle_timeout_or_disconnect` and `reconcile_order`, plus per-fill `qty`/`price`
(relabelled `fill_quantity`/`fill_price` so the reason names the failing side).

Lessons:

- A fabricated zero is only as bad as the decision it feeds. The same syntactic
  bug was cosmetic in an observability column and ledger-destroying where it
  gates a `if value > 0` block. When auditing, check what the parsed value
  CONTROLS, not just where it is written.
- `dict.get(key, "0")` does not catch `{"k": None}` -- the key is present, so the
  default never applies and `Decimal("None")` raises `InvalidOperation`. The
  `, 0` default and the explicit-None case fail DIFFERENTLY, so tests must cover
  both; a helper handling only the missing-key case looks correct and is not.
- `Decimal("NaN")` and `Decimal("Infinity")` PARSE SUCCESSFULLY and then poison
  every downstream comparison (`is_finite()` is required, not just no-exception).
- Parse BEFORE opening `engine.begin()`. Both order-level parses sit ahead of
  the first write, so a payload we cannot trust cannot half-persist a status
  update -- proven by a stub engine asserting `touched_tables == set()`.
- A stub engine that RECORDS statements and exposes `touched_tables` is enough to
  assert "nothing was written" for any method; `statement.table.name` is enough,
  no DB required.
- Fail-closed needs a destination for the exception. Here `worker._run` catches
  any exception and calls `_enter_degraded`, so the raise lands as DEGRADED and
  retries next cycle -- verify that the layer ABOVE actually handles it before
  relying on the docstring claim.
- Do not blanket-apply the pattern. Two sites were deliberately left alone:
  `filled_quantity=Decimal("0")` on the fresh-submit insert is a real literal
  meaning "no fill yet", and `fee` keeps allow-None + swallow-on-parse-error
  because a missing fee is genuinely optional and `None` is meaningful in
  `broker_fills`. "Fail closed" applied to optional fields is just data loss.

Tests: tests/test_executor_broker_numeric_fail_closed.py (11 pure unit tests, no
Postgres/broker/DB mutation). The `dict.get(key, default)` audit is now CLOSED
across guard, worker AND executor.

## Pydantic defaults silently publish zeros in API contracts

`PaperPortfolio.orders_count` / `fills_count` default to `0`
(packages/contracts/paper.py:100-101). `get_broker_portfolio` never passed
them, so the ALPACA PAPER portfolio reported `orders_count_reported: 0` while
carrying 7 populated orders in the SAME payload -- observed live in
`.agent-runtime/paper-latest.json`, where the deliberate
reported-vs-actual mismatch check was failing on both fields.

Lessons:

- A defaulted response field is indistinguishable from a measured zero. When a
  constructor omits a field, the contract does NOT complain -- it publishes the
  default as if it were data. Grep every constructor of a response model and
  compare its kwargs against the model's fields, not just against what the
  endpoint's narrative claims.
- Two independent facts in one payload must be cross-checked. "0 orders" plus
  "7 orders listed" is a self-contradiction that any observer can catch, so
  publish totals and lists together and keep them consistent.
- When a list is `LIMIT`-capped, `len(list)` is NOT a count. It silently freezes
  at the cap, which is a more dangerous lie than 0 because it looks plausible.
  Use `select(func.count()).select_from(<the same join>)` so the count and the
  list are derived from one definition. Also: COUNT semantics must match list
  semantics (same join, same filters, same scoping) or the two fields disagree
  for a different reason.
- This is the OBSERVABILITY twin of the `dict.get(key, 0)` fail-open class
  already recorded for guard/worker/executor: there, an invented zero entered a
  safety comparison; here, an invented zero entered the operator's dashboard.
  Same root cause -- a default substituted for a measurement.
- Pure unit tests are possible for an API route without a DB: call the route
  function directly with a stub `app.state.database` whose stub connection
  dispatches on `str(statement)` (`"broker_fills" in text`, etc.) and serves
  canned rows. `asyncio.run(route(...))` is enough; no TestClient, no Postgres.
  Record the statements so the test can assert a COUNT query was actually
  issued, which is what pins the regression.

Tests: tests/test_broker_portfolio_counts.py (3 pure unit tests).

## A test fixture can contradict the contract it is meant to pin

`_assert_open_orders_known` matches a remote open order with
`by_broker_id.get(id) or by_client_id.get(client_id)` -- the client-id fallback
exists because the broker id is written only after submission returns, so an
order can be working at the broker while only its client id is known locally.

A regression test that built TWO remote orders from one shared fixture default
(`client_order_id=CLIENT_ID` for both) did not fail because of a missing
loop-all-orders check -- it failed because the second order was, correctly,
matched by client id. The assertion was unreachable, and "fixing" the
production code to make it pass would have removed the fallback that the sibling
test `test_match_by_client_order_id_when_broker_id_not_stored_yet` depends on.

Lessons:

- When a helper builds a fixture with sensible defaults, a test needing several
  distinct entities MUST override every identity field, not just the one it
  asserts on. Broker-external identifiers (broker id AND client id) are one
  identity -- varying only one of them is not a distinct entity.
- Before changing production code to satisfy a failing test, ask whether the
  fixture describes a state the real system can produce. A red test is evidence,
  not a verdict.
- Also confirmed while validating: a raise inside this method names the SIDE
  that diverged, and a junk remote size reuses the existing `_decimal` label
  (`invalid_broker_open_order_notional`), so it still fails the whole cycle
  closed rather than being treated as equal to the approved size.

Tests: tests/test_worker_reconcile_unknown_open_orders.py (17 pure unit tests).

## Verify lint regressions by line location, not by an out-of-tree HEAD copy

To check whether WIP added ruff errors to a file that already had some, a
tempting move is `git show HEAD:<file> > $TMP/x.py && ruff check $TMP/x.py`. That
comparison is UNSOUND: ruff resolves config (line-length, per-file ignores) from
the nearest pyproject/ruff.toml relative to the FILE, so the temp copy loses the
repo's config and reports a different, smaller error count. It produced 1 vs 7
here and would have "confirmed" a clean bill of health.

Cheap correct method: run ruff on the working-tree file once with
`--output-format=concise` and read the line numbers of every finding. If they all
fall in lines that predate the diff, the WIP added none. One command, no copy.

## A reconcile timestamp is not a submit timestamp

`get_broker_portfolio` mapped `PaperOrder.requested_at = o["last_reconciled_at"]`.
That column lives on `broker_orders` and is bumped on EVERY reconciliation cycle,
while the fills in the SAME payload carry `filled_at` derived from the true submit
time. The result was self-contradictory output: Mission Control could render a
fill that appears to have happened BEFORE the order that produced it, and the
reported order time drifted forward continuously on a healthy runtime.

`paper_orders.requested_at` is the immutable submit time, is `nullable=False`,
and was already JOINed in the existing query -- the correct value was in the row
and simply not selected.

Lessons:

- A "timestamp" column name is not a contract. Before binding a DB column to a
  response field, ask WHAT WRITES it and HOW OFTEN. Anything a periodic job
  refreshes is not a record of when an event occurred.
- When a query already joins the table that holds the truth, treat "the field
  comes from the wrong table" as a likely defect rather than accepting a
  convenient column of the same type. Two fields of the same type in one row are
  a trap, not a convenience.
- Pin such a bug with fixtures that make the two candidate values DISTINCT by a
  wide margin (2h apart here). If a test fixture uses one timestamp for both
  fields, the test cannot tell a correct mapping from the wrong one -- it passes
  against the bug.
- Comparing timestamps as ISO STRINGS is flaky: fractional-second presence
  differs between renderings. Parse to `datetime` in the assertion.

Tests: 2 pure unit tests in tests/test_broker_portfolio_counts.py (fixture now
carries both timestamps deliberately distinct) plus 1 DB-backed sibling in
tests/test_broker_routes.py. The pure-unit twin is the executable coverage:
the DB-backed file cannot run without Postgres.

## Sort keys are claims too: a heartbeat column is not an event time

Third member of the "wrong column, right type" family on this route (the first
two were `requested_at` bound to a reconcile timestamp and unset contract
fields). `get_broker_portfolio` ordered `portfolio.orders` by
`broker_orders.last_reconciled_at DESC`. That column is re-stamped on EVERY
reconciliation write (executor.py:69, :89, :153, :215) -- it is a liveness
heartbeat, not a record of when the order happened. Two consequences, both
operator-visible:

- an order still working at the broker carries the newest timestamp forever and
  is pinned to the top of the list, so a "newest first" order list was not
  newest first, and it contradicted the `requested_at` reported in the same
  row (fixed in the previous cycle);
- under `LIMIT 100`, old still-open orders crowd out genuinely newer trades.

Fix: order by `paper_orders.requested_at DESC` plus `symbol` and `order_id` as
tiebreakers. `paper_orders.order_id` is the PRIMARY KEY and `symbol` /
`requested_at` are NOT NULL (migration 0008), so the ordering is a TOTAL order
and the capped window is deterministic instead of shuffling.

Lessons:

- Audit `ORDER BY` keys with the same suspicion as response-field bindings:
  ask what WRITES the column and HOW OFTEN. A column refreshed every cycle is
  useless as an ordering key no matter how natural the name looks.
- An `ORDER BY` is a claim about importance ("newest first") that the payload
  then contradicts. If the list is presented in an order, that order must be
  derived from the same field it reports.
- `LIMIT` + a non-unique sort key = an unstable window. Add tiebreakers up to a
  unique/PK column so pagination cannot reshuffle between identical queries.
  Confirm the tiebreaker's uniqueness and nullability in the migration, not by
  assumption.
- `last_reconciled_at` is still worth REPORTING per order (it answers "is the
  broker picture current for this order?") -- it is only wrong as a SORT key.
  Fixing the mapping does not mean the field is useless.

Tests: 2 pure unit tests in tests/test_broker_portfolio_counts.py. They read
the compiled SQL out of the stub connection's recorded statements and split on
`ORDER BY`, because the projection itself mentions `last_reconciled_at` via
`broker_orders.*` -- asserting on the whole statement text would be ambiguous.

## Running pytest here requires overriding two ambient env vars

The agent shell exports `DATABASE_ROLE=runtime` and `EXECUTION_MODE=alpaca_paper`.
Both make `tests/conftest.py::pytest_configure` call `pytest.exit(...)`, and the
symptom is a confusing refusal rather than a test failure:

- `DATABASE_ROLE=runtime` -> "REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE"
  (the guard is correct and must not be weakened).
- `EXECUTION_MODE=alpaca_paper` -> the same refusal message with
  `configuration_error: missing_alpaca_credentials`, because
  `Settings.model_validator` requires Alpaca creds when the execution mode is
  `alpaca_paper`. The repo has only `.env.example`, and conftest only sets
  `MARKET_DATA_PROVIDER=simulator` in an autouse FIXTURE, which runs after
  `pytest_configure` -- so the configure-time `Settings(_env_file=None)` check
  fails first.

Working command (no credentials needed, no .env read):

    DATABASE_ROLE=test EXECUTION_MODE=local_paper MARKET_DATA_PROVIDER=simulator \
      C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-unified/.venv/Scripts/python.exe \
      -m pytest tests/<file>.py -q

Do not "fix" this by editing conftest or by relaxing the database guard.

## Unit-testing a DB-driven worker method without Postgres

`_process_pending_submits` looks untestable without a database, but it is not.
Everything it needs can be injected:

- `self.engine` only ever calls `connect()` / `begin()`, then
  `execute(...).mappings()` (`.first()` for the single system_controls row, and
  iteration for the pending/in-flight row sets) and `scalars(...)` for
  blocked_symbols. A scripted connection that returns canned rows IN CALL
  ORDER covers all of it: system_controls first, then pending rows, then
  in-flight rows.
- `self.executor` is an attribute, so replacing it with a recorder makes the
  exact `submit(...)` kwargs observable -- which is the assertion that matters,
  because the quantity handed to submit IS the trading decision.
- `self.degraded` / `self.reconciliation_ready` are plain attributes; set them
  to reach the real body instead of the early return.

Result object must support `mappings()` returning something iterable (the
pending fetch iterates it) plus `.first()` and `.all()`. One small class covers
all three.

Method under test: `worker._process_pending_submits(account=..., positions=...)`
is async but does no real I/O in the tested path, so
`asyncio.run(...)` is enough -- no pytest-asyncio needed.

The guard is NOT stubbed. Running `ExecutionGuard.evaluate` for real makes the
"nothing was submitted" assertions meaningful (they prove the guard's SELL
branch short-circuits) and, incidentally, covers the guard/worker wiring that
the earlier "test the wiring, not just the unit" lesson calls for.

## Asserting a rejection reason without a DB

The guard's rejection path executes
`update(risk_decisions).values(decision="REJECTED", reason=reason)`. To assert
WHICH condition rejected, filter the recorded statements by class name
(`statement.__class__.__name__ == "Update"`) and read
`statement.compile().params["reason"]`. This turns a generic "nothing was
submitted" into a specific cause, which is what makes the test a regression
guard rather than a smoke test.

Tests: tests/test_worker_pending_sell_sizing.py (13 pure unit tests).

## The two sides of the order builder are asymmetric

`_process_pending_submits` builds one order per APPROVED decision and the branches
are NOT symmetric:

- SELL sends SHARES: `quantity = broker_quantity - pending_sell_quantity`,
  `notional = None`.
- BUY sends DOLLARS: `quantity = Decimal("0")`,
  `notional = ExecutionGuard.MAX_NOTIONAL_PER_TRADE` (worker.py:424-426).

Both go through the SAME `ExecutionGuard.evaluate` call and the SAME
`executor.submit` call, so testing one side leaves the other entirely
uncovered. A BUY that leaked a share quantity would size a dollar decision as a
number of shares -- the wrong order, not just a wrong quantity.

Invariant worth pinning in tests: the guard CHARGES
`MAX_NOTIONAL_PER_TRADE` against `MAX_TOTAL_EXPOSURE` when approving a BUY
(guard.py:160-168), so the notional the worker submits must be exactly that
constant. If the two diverged, the exposure cap would be enforced against a
figure no order ever used. Assert against `ExecutionGuard.MAX_NOTIONAL_PER_TRADE`
(not a literal 10.00) so changing the constant in only one place fails the test.

Exposure-cap boundary tests are worth having in BOTH directions: with existing
exposure making `total + MAX_NOTIONAL == MAX_TOTAL_EXPOSURE` the BUY is
approved (the guard uses `>`), and one cent more is rejected. A single "over the
cap" test would not catch an off-by-one that flipped to `>=`.

The fail-closed asymmetry is also worth one explicit test: under an account
missing `last_equity`, a BUY is rejected and a SELL of an existing position
still submits `quantity=10, notional=None`. That pins "fail closed" as
BUY-only rather than a blanket shutdown.

Tests: tests/test_worker_pending_buy_notional.py (15 pure unit tests).

## The execution gate is NOT a health signal

`AlpacaPaperWorker.reconcile_once` deliberately closes the EXECUTION gate at
the top of every 3s cycle:

    self.reconciliation_ready = False
    self.degraded = True
    self.degraded_reason = "reconciliation_in_progress"

and reopens it only after the broker picture is fully refreshed. That is correct
for trading -- no order may be placed against half-refreshed state -- but it
means `degraded` is True for a slice of EVERY cycle even in a perfectly healthy
runtime. Reading it as a health signal made `/health` flap to 503 in normal
operation; runtime evidence was decisive: samples reported
`health.status=degraded` while `paper.degraded=false`, `reconciled=true`,
`paused=false`, each taken ~3.0-3.9s after its own `last_reconciled_at`, i.e.
inside the NEXT cycle's window.

The lesson generalizes: a flag that exists to fail CLOSED for one subsystem
(here, trading) must not be reused as a report of whole-runtime health. Separate
the two, and keep the sentinel EXACT -- only the literal
`"reconciliation_in_progress"` is excused, so any real error still reads as
unhealthy. A boolean alone is not enough: `_enter_degraded` must latch a
durable `has_reconciled = False`, otherwise the next cycle's in-progress
sentinel would self-heal a runtime that is failing every single cycle.

Second defect found in the same handler: `response.status_code` was assigned
BEFORE the ALPACA PAPER worker check narrowed `ready`, so the endpoint could
return HTTP 200 next to a body saying `degraded`. Compute every verdict, then
assign the status code once. In the non-paper branch `ready` is not modified,
so moving the assignment is behavior-preserving there.

`worker.health_ready()` had exactly ONE caller (`/health`); the trading
decisions at worker.py:313, 359 and 423 read `degraded` /
`reconciliation_ready` and were deliberately left untouched.

Tests: tests/test_health_paper_worker_ready.py (11 pure unit tests).

## Distinguish "fail closed on this order" from "fail the whole worker"

`_process_pending_submits` raised
`RuntimeError("sell_quantity_unavailable:<symbol>")` when the computed SELL
quantity was `<= 0`. `_run` (worker.py:97-99) maps ANY RuntimeError to
`_enter_degraded`, and `_enter_degraded` releases NO further execution for the
REST OF THE PROCESS LIFETIME. So one unexecutable decision stopped the whole
bot. That is not fail-closed, it is fail-catastrophic: the condition had
already been decided correctly upstream by `ExecutionGuard` (which rejects
`available_qty <= 0`), so the raise escalated an ordinary, expected outcome into
a permanent halt.

Fixed by skipping the row instead: the same REJECTED write-back the guard's own
rejection branch uses, a warning log, and `continue`. Fail-closed preserved
(nothing submitted, reason persisted for the operator), blast radius reduced
from "worker, permanently" to "one decision, retried next cycle".

Lessons:

- Audit every `raise` in a hot decision loop against what the CALLER above does
  with it. On this worker, raise == permanent DEGRADED, not "skip this order",
  so the blast radius of a throw is the whole trading process. Classify each
  raise: is the condition a safety invariant (must halt) or an expected
  per-order outcome (must skip)?
- The two available outcomes are not symmetric: for an unexecutable order,
  write the decision back as REJECTED with a reason and move on. That is
  STRICTLY more informative than raising, because the halt also destroys the
  per-order reason.
- Reachability was found by a TEST, not by reading the raise: the guard dedupes
  positions per symbol (`pos_map = {p["symbol"]: p for p in positions}`,
  guard.py:80, LAST row wins) while the worker SUMS all rows for a symbol
  (worker.py:436-443). A payload with two netting rows for one symbol makes the
  guard approve a SELL the worker computes as 0. When two components consume the
  same list, check that they AGGREGATE it the same way -- disagreement is silent
  and shows up only as an impossible downstream value.
- When the payload is something a broker can legitimately send (multiple rows
  for one symbol), prefer writing a test with that exact payload over reasoning
  about whether the line is reachable.
- A test for a skip must also assert the LOOP CONTINUES: submit a second,
  healthy pending SELL in the same cycle and assert it still reached
  `executor.submit`. "nothing submitted" alone passes for a `return` as happily
  as for a `continue`.
- Frozen runtime evidence for the same window: three tiny fractional-share
  positions (AAPL/SPY/TSLA, ~0.01-0.03 shares each) from notional BUY orders,
  11 orders/11 fills, unrealized P&L -0.008836. Healthy but it confirms
  dollar-notional BUYs are being converted to fractional share positions, so the
  multi-row-per-symbol question is worth closing deliberately rather than
  assuming Alpaca always sends one row.

Tests: 3 pure unit tests added to tests/test_worker_pending_sell_sizing.py
(now 16 pure unit tests total).

## mypy scope on this repo

- `[tool.mypy] files = ["services", "packages",
  "infrastructure/docker/migrations"]` -- `tests/` is NOT in mypy's scope.
- Running mypy on a test file by hand reports `no-untyped-def` /
  `no-untyped-call` errors. Those are pre-existing convention, not a
  regression: tests/test_daily_loss_equity_missing.py reports the same class of
  error. Do not "fix" them and do not treat them as a failure.
- Validate types with `mypy services/alpaca_paper` (the configured scope), and
  use ruff plus pytest for the new test file.

## Testing on this Windows host

- The default `python` on PATH is Hermes' own 3.14 and has NO pytest.
- Use the project venv interpreter for every pytest/ruff/mypy run:
  C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-unified/.venv/Scripts/python.exe
  (run it with workdir set to the TradingBot-agent repo)
- Postgres is not running in the agent environment, so DB-backed tests fail at
  fixture setup with psycopg ConnectionTimeout. These are environmental.
  tests/test_replay_live.py also fails on Windows for lack of ComSpec/SystemRoot.
- Check whether a failure happens at SETUP before treating it as a regression.
