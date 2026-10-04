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

## Contract Literals must be no narrower than the DB CHECK constraint

When a pydantic `Literal` enumerates a value that a DB CHECK constraint also
enumerates, the two lists must match. A `Literal` narrower than the constraint
cannot be filled from a valid row: the API layer either silently publishes the
wrong default or raises `ValidationError` on legal data, and both look like
application bugs. Here `mode` was `Literal["REPLAY"]` in the page contracts
while `ck_paper_run_mode` admits `('REPLAY','ALPACA_PAPER')` — so the deployed
mode was unrepresentable. When you touch a `Literal`, read the migration's
CHECK constraint in the same breath; if you cannot find the constraint, the
Literal is a guess.

Corollary: a field with a hardcoded default in a contract is a silent
lie-generator. Any endpoint serving a live run must pass the real value
explicitly, and a test must assert the non-default value — asserting the
default proves nothing.

## Test fixtures must match the shape of the thing they stub (recurring)

Third occurrence of one class. A stub that is subtly unlike the real object
makes its own test unfalsifiable or wrongly red, and you cannot tell a fixture
bug from a product bug without reading the contract. Three variants hit in a
row: a stub lacking `__iter__` where production iterates; a fixture omitting a
required field with no default so pydantic rejects it before any assertion
runs; a stub minting a FRESH object per call so per-call state (a `run_id`)
disagreed with the assertion's own reference. Rule: when a WIP test is red,
read the contract's field list and the stub's construction before touching
production code — a red test is not evidence about production. Build the stub's
object ONCE, outside the fake, and serve that single instance.

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

## NULL is a legal value; coerce it only after knowing why it is NULL

`get_broker_portfolio` published `PaperOrder.quantity` from
`broker_orders.requested_quantity`, but `executor.py:151` writes
`requested_quantity=quantity if notional is None else None` -- a NOTIONAL BUY
is denominated in dollars, so the share count is unknowable until the broker
fills and NULL there is correct BY DESIGN, not missing data. The route's
`Decimal(str(o["requested_quantity"] or 0))` turned that deliberate NULL into
`quantity: "0"` on FILLED trades; the live snapshot showed three FILLED orders
(AAPL/SPY/TSLA) at `"quantity": "0"` opening positions of 0.0299 / 0.0129 /
0.0268 real shares. Fallback to `filled_quantity` when `requested_quantity` is
NULL restores the truth, and a partially filled notional order reports its
filled share count rather than zero.

Lessons:

- Before coercing a NULL to a default, find the writer and ask whether the NULL
  is a MEANINGFUL state. One grep of the INSERT that owns the column
  (`grep requested_quantity` -> executor.py) settles it; guessing "missing
  data" would have preserved the lie.
- Distinguish "absent" from "not applicable". `requested_quantity is None` is
  not the same claim as `requested_quantity == 0`, and `or` / `??` treats them
  as identical -- so a legitimately-zero quantity and an unset one cannot share
  a branch. Test the None case explicitly.
- A zero in a response is a claim. If the code cannot distinguish "traded
  nothing" from "does not know how much", it must not emit `0` -- publishing an
  invented zero is the same root cause as `dict.get(key, 0)` reaching a safety
  comparison, just aimed at the operator instead of the guard.

## A WIP test can be red because its FIXTURE was never extended

Three new tests in tests/test_broker_portfolio_counts.py passed
`requested_quantity=` / `filled_quantity=` / `status=` to `_order_row`, a helper
whose signature still accepted only `requested_at`. All three raised
`TypeError` at the fixture call -- never reaching an assertion -- so the suite
was red for a reason unrelated to the defect under test, and the correct fix was
one line of fixture plumbing, not the production logic.

Lessons:

- `TypeError` on a helper argument is a fixture gap, not a product defect. Read
  the error's origin before assuming the production change is wrong; changing
  `broker_routes.py` to satisfy it would have hidden the real NULL-coercion bug
  behind a green test.
- When extending a shared fixture helper, keep every existing default
  byte-compatible (keyword-only, with the old default) so the 18 prior callers
  are provably unaffected -- then run the WHOLE file, not just the new tests,
  to prove it.
- A docstring on the helper is where the fixture's legality is argued. Note
  explicitly WHY a NULL/None value is reachable in the real system, or the next
  reader will "clean it up" back into a fabricated number.

Tests: tests/test_broker_portfolio_counts.py (21 pure unit tests).

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

## Symmetric fail-closed branches are usually a coverage hole, not a code bug

`_assert_open_orders_known` compares size two ways: the BUY branch raises
`broker_order_notional_divergence` unless BOTH `remote.notional` and
`local.requested_notional` are present and equal; the SELL branch raises
`broker_order_quantity_divergence` under the same both-present rule for
`remote.qty` / `local.requested_quantity`. Reading them side by side makes the
SELL branch look like it would accept a NULL local size as a match -- it does
not. Both branches already fail closed; only the TESTS were asymmetric
(BUY had broker-side-missing and local-side-missing, SELL had only
broker-side-missing).

Lessons:

- When a task says a fail-closed path "has no coverage", check whether a
  SIBLING branch for the other side already has it, and read the production
  branch before assuming a defect. Two of three candidate defects this cycle
  resolved to "already fixed on the frozen runtime", and this one to "already
  correct in production, untested in one direction".
- A NULL size column must never be read as "size zero matches". `requested_quantity`
  is NULL for every notional order, and every execution gate sizes a SELL from
  that column, so an unsourceable value is unknown -- not equal to anything.
- Keep the new test byte-compatible with the family's shared helpers
  (`_local_row`, `_remote_order`) so it inherits their docstrings and
  defaults; only override what the case asserts on.

Tests: tests/test_worker_reconcile_unknown_open_orders.py (18 pure unit tests).

## Testing on this Windows host

- The default `python` on PATH is Hermes' own 3.14 and has NO pytest.
- Use the project venv interpreter for every pytest/ruff/mypy run:
  C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-unified/.venv/Scripts/python.exe
  (run it with workdir set to the TradingBot-agent repo)
- Postgres is not running in the agent environment, so DB-backed tests fail at
  fixture setup with psycopg ConnectionTimeout. These are environmental.
  tests/test_replay_live.py also fails on Windows for lack of ComSpec/SystemRoot.
- Check whether a failure happens at SETUP before treating it as a regression.

## Fail-closed is per-entity; the blast radius decides whether it escalates

`AlpacaPaperExecutor._required_decimal` raising `RuntimeError("invalid_broker_*")`
on one order was CORRECT -- and `_reconcile_active_orders` still degraded the
whole worker on it. The loop called `executor.reconcile_order` unguarded, so a
single unsourceable broker numeric for ONE order aborted every remaining order
in the batch (fills unrecorded, in-flight exposure stale) and escaped to `_run`,
whose `except Exception` calls `_enter_degraded` -- releasing NO further
execution for the REST OF THE PROCESS LIFETIME. An availability failure wearing
fail-closed clothing: fail-closed was per order, but the handler was per
process.

Fix: `except RuntimeError` scoped to the single call, a warning naming the
order, loop continues. The bad order still writes nothing and keeps its prior
status, so it stays in `ACTIVE_ORDER_STATUSES` and is RETRIED next cycle --
fail-closed preserved, blast radius cut from "worker, permanently" to "one
order, one cycle".

Lessons:

- For each `raise` on this worker, ask THREE questions, not one: (1) is the
  condition a safety invariant (must halt) or an expected per-entity outcome
  (must skip)? (2) what is the ESCAPE RADIUS -- is the handler above it per
  entity or per process? (3) after the skip, is the entity RETRIED, marked
  terminal, or silently dropped? A per-entity fail-closed inside a per-process
  fail-closed handler is fail-CATASTROPHIC regardless of how correct the raise
  is.
- Narrow the `except` to the class the callee actually raises. Grepping the
  callee for `raise` is the cheap proof that the new handler cannot swallow a
  safety invariant: `reconcile_order` raises only `invalid_broker_*`
  (executor.py:40,42), while the whole-cycle `broker_order_*_divergence`
  invariants raise from `_assert_open_orders_known`, called by `reconcile_once`
  (worker.py:150) OUTSIDE the loop -- so they still degrade the cycle, which is
  correct because a payload-wide mismatch really is a whole-cycle problem.
  Locating the call is what makes the fix auditable instead of merely green.
- A test fixture that instantiates the real object inherits its REAL startup
  state. `AlpacaPaperWorker.__init__` deliberately opens fail-closed
  (`degraded=True`, `reconciliation_ready=False`,
  `degraded_reason="startup_reconciliation_pending"`) and only `reconcile_once`
  clears it, which needs the adapter/DB the test avoids. Three tests were red
  for that reason. The fix is the FIXTURE (set the post-reconcile state
  explicitly, with a comment saying why), NOT `__init__` -- "opening
  fail-closed at startup" is the production invariant. Same shape as the
  `_order_row` fixture lesson above.
- Assert the DEFERRED entity is retried, not just skipped: reconcile a batch
  again with the fault removed and assert it then completes normally. That
  pins "deferred", which is what makes the skip safe, rather than "dropped".
- A stub engine whose `scalars()` returns an iterator and whose `execute()`
  returns self covers this loop entirely; `asyncio.to_thread(fetch_active)` only
  needs `connect()` as a context manager.

Tests: tests/test_worker_reconcile_isolates_bad_order.py (7 pure unit tests).

## Never re-derive a mapped value from its raw source; and watch for column shadowing

`get_broker_portfolio` published `status=o["status"].upper() if o.get("status")
else "UNKNOWN"` -- it re-computed the user-facing status from the RAW
`broker_orders.status` string instead of reading the one the executor had
already mapped into `paper_orders.status`. `.upper()` is correct for exactly the
ten states in `AlpacaPaperExecutor._map_status`, and Alpaca also emits states
OUTSIDE that map (`done_for_day`, `halted`, `suspended`, `stopped`,
`pending_replace`, `calculated`, ...). Those uppercased strings are absent from
the `PaperOrder.status` Literal, so pydantic rejected the ROW and one unfamiliar
order status 500'd the ENTIRE portfolio endpoint -- positions, counts and every
other order lost over one string. Verified against pydantic: 7/7 rejected.

Lessons:

- If a component already MAPS a broker enum into your contract, the consumer
  must read that mapping. Re-deriving the value with a transformation
  (`.upper()`, a dict, a cast) silently re-implements the map in a second place
  with no test coverage outside the mapped set.
- Blast radius scales with where validation happens: a bad ENUM member fails the
  whole response model, not one field, so a per-row data quirk becomes a
  total endpoint outage. Prefer a source that is guaranteed in-domain over one
  that must be normalized at read time. `paper_orders.status` is NOT NULL and
  CHECK-constrained to the contract Literal (`ck_paper_orders_state_m7`,
  migration 863267844740) and degrades unfamiliar broker text to UNKNOWN, which
  is exactly the fallback wanted.
- When a query does `select(broker_orders, ...)` (a whole-table expansion) AND
  joins a table with a same-named column, an unlabelled extra column does not
  add a key -- it collides with the existing one, and the row resolves to the
  FIRST expanded match, i.e. the raw broker text again. Select it under an
  explicit `.label("paper_status")` and pin that label in a test by reading the
  compiled SQL out of the stub connection's recorded statements.
- A fixture that derives the two candidate values from ONE source cannot detect
  this class of bug: `status` (raw broker text) and `paper_status` (mapped local)
  needed separate keys with separate, deliberately DISAGREEING defaults, plus an
  assertion that the reported value is not the uppercased broker string --
  otherwise the test passes against the bug it is meant to pin.
- Keep the raw value reachable in its own response field (`broker_status`)
  instead of discarding it. The mapping is for the CONTRACT; the operator still
  needs what the broker actually said.

Tests: tests/test_broker_portfolio_counts.py (19 pure unit tests; 3 new, 9
cases with parametrization) plus a DB-backed sibling in
tests/test_broker_routes.py (collects cleanly; runs when Postgres is up).

## One rejection string can hide two different remediations

- When a single `raise` (or rejection message) covers two distinct broker
  realities, an operator reading only that string cannot act on it. Split the
  string BEFORE splitting any behaviour, and leave the pre-existing string on
  the branch that already had it so existing log greps keep matching.
- Pin the split by asserting the OTHER reason is ABSENT from the message, not
  just that the new one is present. A test that only asserts
  `pytest.raises(..., match="new_reason")` still passes if both causes keep
  collapsing into that one string.
- Check the LAYER before calling a branch dead code. Here
  `ExecutionGuard._net_positions` (commit abe7d25) nets duplicate position
  rows, which made the worker's duplicate-symbol check look redundant; reading
  the call sites showed the worker validates the RAW broker rows and only the
  guard nets them downstream. Grep every call site and trace where the argument
  came from before deleting a check that looks unreachable.

## Contract defaults are silent lies; grep every constructor of a shared contract

`PaperPortfolio` has exactly TWO constructors (`services/api/broker_routes.py`
and `services/api/paper_queries.py`). The broker one passed `mode=`; the
simulator one passed `status` and `provider` but not `mode`, so pydantic
supplied its default `"REPLAY"` and the endpoint labelled an `ALPACA_PAPER`
book as REPLAY. A default that is only correct for the common case is a lie for
every other case, and nothing in the code or the type system says so.

- When a contract model has a defaulted field, audit EVERY constructor against
  the field list, not just the one that looks suspicious. `grep -n "PaperPortfolio("`
  is the whole search.
- Severity ranking inside one payload: a wrong `quantity` misreports one order,
  a wrong `status` can invalidate the whole model, a wrong `mode` misattributes
  the executor for every number in the response. Check the blast radius before
  picking what to fix.
- `paper_runs.mode` is UPPERCASE `'REPLAY'|'ALPACA_PAPER'`
  (`ck_paper_run_mode`, dropped and recreated by migration
  `f2c8a51d9b10_paper_v1_runtime_mode.py`; the original 0008 constraint allowed
  only REPLAY). It is deliberately identical to the `PaperPortfolio.mode`
  Literal, so a correct read needs NO translation. A test that feeds lowercase
  `alpaca_paper` asserts a value the database can never hold and the model would
  reject -- check the CHECK constraint before writing the fixture value.
- Stubs for `Connection.execute(...).mappings()` need `__iter__` as well as
  `.first()`/`.one()`/`.all()`. `paper_queries.portfolio` builds a `marks` dict by
  iterating `.mappings()` directly, so a stub with only the named accessors
  raises `TypeError: '_Mappings' object is not iterable` and masks every
  assertion in the test. Iterate the stub the way production does.

## A grep-verified schema assumption is not a contract; pin it as a test

The worker's `_save_broker_snapshot` deliberately RAISES on a missing broker
`buying_power` instead of writing NULL, and that is only correct while
`broker_portfolio_snapshots.buying_power` is NOT NULL. The column was created
NOT NULL in `db6f20ef0e19` and the "nothing later alters it" half was verified
by grep and recorded in prose only -- the two sides of a cross-file contract
(runtime code in services/, schema in infrastructure/docker/migrations/) can
drift with nothing failing at the time.

- When a decision in AGENT_STATE.md depends on a schema property, convert the
  prose claim into a test that FAILS when the property is gone. A grep result
  recorded once is a snapshot, not a guard.
- Cover BOTH sides of such a contract plus the "nothing else touched it" hole:
  the model metadata, the creating migration's declaration, and a scan that no
  other migration in `versions/` references the table (a future
  `op.alter_column` relaxes the column without editing the creating file).
- Keep the anti-vacuity test. "Every column the write fills is NOT NULL" passes
  trivially if the write stops filling them, so pin one known field explicitly
  (`buying_power`) and, on this repo, remember `_save_broker_snapshot` fills ALL
  8 columns, so the generic check has no blind spot.
- Prove non-vacuity by mutation instead of reasoning: flip
  `c.buying_power.nullable = True` in memory, and for the file-reading tests
  copy the migration into a temp dir and repoint the module constant. Never edit
  `infrastructure/docker/migrations/` or any tracked file to test the guard --
  a stub engine that records `connection.execute` needs no database at all.
  Worth doing: the memory-only mutation and the temp-dir migration mutation
  each caught that the corresponding test really does fail.
- `on_conflict_do_update` compiles the SET clause's `excluded.<col>` references
  into `statement.compile().params` too, so filter the param names against the
  table's real columns (`name in <table>.c`) before asserting on them.

## Two blast radii in one loop: read WHICH raise you are wrapping

`_reconcile_active_orders` catches a RuntimeError PER ORDER;
`_assert_open_orders_known` two steps later is not wrapped and must not be. Same
cycle, same class of fault, opposite blast radius, on purpose:

- a per-order fault ("this order's numerics cannot be sourced") has a safe
  local answer -- leave it ACTIVE, fabricate nothing, keep going;
- the account-wide assert answers "is the broker's whole open-order book known
  to us?", and every one of its failure modes is account-wide by construction
  (unknown live order, terminal-status divergence, symbol/side divergence).
  Scoping any of those to one order leaves the rest verified against a picture
  already proven wrong, and then the cycle reaches `_save_broker_snapshot` and
  flips `reconciliation_ready`/`has_reconciled` True -- a fail-OPEN, strictly
  worse than degrading.

Reusable rules:

- When you add a try/except around a fault, first write down whether the fault
  is per-item or per-collection. "Catch and continue" is only correct for the
  first. Wrapping the second deletes the fail-closed guarantee silently,
  because every assertion still passes on the healthy path.
- Pin BOTH halves of a deliberate asymmetry. Pinning only the per-order half
  (here `test_worker_reconcile_isolates_bad_order.py`) leaves the account-wide
  half unpinned, and the next cycle can read the missing test as permission to
  wrap it. See tests/test_worker_unknown_order_aborts_whole_cycle.py.
- A control test ("the verified path still works") is what stops the fail-closed
  test from passing vacuously. It must reach the real downstream writer, so its
  stub must satisfy that writer: `_save_broker_snapshot` reads cash, equity,
  portfolio_value and buying_power unconditionally and raises
  `invalid_broker_<field>` on a missing one. A stub returning
  `{"status": "ACTIVE"}` makes the control assert the writer's failure instead
  of the property under test. Build the stub from what the called code reads,
  not from what the test cares about.

## A dict of ROWS silently lets two remote items resolve to one local row

The highest-value shape found by auditing reconciliation for "does this assert
the COUNT or just the contents": the per-item checks all passed, and the batch
still reconciled a state that does not exist.

`_assert_open_orders_known` mapped broker open orders onto local
`broker_orders JOIN paper_orders` rows with two dicts holding the rows
themselves:

    by_broker_id = {row["broker_order_id"]: row for row in rows if row["broker_order_id"]}
    by_client_id = {row["client_order_id"]: row for row in rows}
    local = by_broker_id.get(broker_id) or by_client_id.get(client_id)

Two DISTINCT broker orders can land on the SAME row -- one matching on
`broker_order_id`, the other falling through to `client_order_id`. Each remote
order then passed its own symbol/side/size checks, so the loop reported success
while the derived exposure counted one local row for two live orders. The same
rows are reused as the guard's `in_flight` in `_process_pending_submits`, so the
undercount reaches risk decisions, not just reporting.

The tell, and the general rule:

- If the thing being derived counts the KEYS of your local collection
  (rows, orders, positions) rather than iterating them, then "each remote item
  found a plausible local match" is NOT sufficient. You must also prove the
  mapping is injective -- no local row claimed twice. Otherwise you have
  converted a per-item assertion into a silent per-collection lie.
- Index instead of holding the object. `{row: ...}` becomes
  `{row: index}` and the index is what you track:

      by_broker_id = {row["broker_order_id"]: i for i, row in enumerate(rows) if row["broker_order_id"]}
      by_client_id = {row["client_order_id"]: i for i, row in enumerate(rows)}
      claimed: set[int] = set()
      ...
      if index in claimed:
          raise RuntimeError("broker_open_order_duplicate_for_local_order:" ...)
      claimed.add(index)

  Holding the object cannot express "already used"; holding the index can.
- TWO lookup paths that fall through to each other (`or`, or `if x is None`)
  are a mutual bypass waiting to happen: each path alone is unique, together
  they can both reach the same row. Any multi-key resolution needs a claim set
  keyed on the RESOLVED TARGET, not on the key that happened to match -- and a
  test that exercises one match via each path (see
  `test_second_order_matching_on_client_id_only_also_raises`).
- Fail-closed ORDER is part of the contract. Check `index is None` (unknown)
  before `index in claimed` (duplicate), or an unknown order gets reported as a
  duplicate and the operator loses the real cause. Pin it:
  `test_duplicate_detection_does_not_mask_the_first_order_missing_locally`.

- Always ship the positive control with the guard. `test_two_distinct_local_rows_each_matched_once_pass`
  exists so a later cycle cannot "fix" a too-eager duplicate check by refusing
  every multi-order cycle. A guard with no control can only ever be tightened,
  never verified.

- Proving non-vacuity without breaking the tree: replay BOTH strategies in a
  scratch script over the same inputs (old dict-of-rows vs new index+claimed
  set) and print the outcome. That gave `OLD: 2 rows matched, raised None` vs
  `NEW: 1 row claimed, raised broker_open_order_duplicate_for_local_order`,
  plus the control `claimed = 2 raised = None`. `git show HEAD:<file> |
  grep -c <new_symbol>` returning 0 confirms the guard is genuinely new. No
  tracked file was edited, no known bug restored in-repo.

## Ruff is part of "done", not a follow-up

An uncommitted WIP can be functionally correct and still un-committable: this
one shipped two `E501 Line too long (104 > 100)` lines in a new test (repo
`line-length = 100`, `select = ["E","F","I","UP","B"]`). Running ruff over BOTH
changed files in recovery mode found it in one call. A dirty tree means the
previous cycle stopped before validation, so assume validation is incomplete
rather than assuming it passed.

## Read-only JSON inspection: `python -c` is blocked unattended

`python -c "import json; ..."` is refused in a non-interactive session
("script execution via -e/-c flag"), and so is `execute_code`. The working
alternative for inspecting `.agent-runtime/paper-latest.json` (or any JSON
artifact) is a small `write_file` script into the scratch dir followed by
`python <script>`. Worth 2 tool calls and fully offline/read-only -- no broker
and no runtime DB is touched.

Related: printing only what a question needs beats dumping the file. The
observation JSON is ~15 KB with a nested `paper`/`health` shape, and one dump
truncated before the keys of interest. A 20-line script that prints
`paper` keys, the count pairs and the position symbols answered the whole gate
in one call.

## Reported-vs-actual mismatches on the frozen runtime are usually UNDEPLOYED fixes

The Paper gate compares `orders_count_reported` vs `_actual` and
`fills_count_reported` vs `_actual`, and on the frozen runtime the reported side
is persistently 0 while the actual side grows (7 -> 13 orders over recent
cycles). That is NOT a new anomaly: the `get_broker_portfolio` counts fix is
committed in this repo and the frozen runtime still runs the pre-fix code,
because deploying to it requires human approval. Same cause for
`health.status=degraded` while `paper.degraded=false` -- the `/health`
execution-gate flap is fixed here, not there.

Rule: before treating a repeated reported-vs-actual mismatch as a fresh bug,
check AGENT_STATE for a committed fix on this branch. A mismatch that has a
fix in HEAD and a live runtime without it is a deployment gap, and re-fixing it
in code produces duplicate work and a second commit claiming the same defect.
The growing `_actual` side is positive evidence the runtime itself is healthy.

## A test asserting a flag the design clears ELSEWHERE is a design misunderstanding

The WIP version of that test asserted `has_reconciled is False` immediately
after `reconcile_once` raised. It failed, and the failure was correct:
`reconcile_once` clears only the per-cycle bits
(`reconciliation_ready`/`degraded`/`degraded_reason`), and `_enter_degraded`
(worker.py:295-301) is the thing that latches `has_reconciled = False`. A raise
alone is not a signal; `_run` decides what to do with it.

- When a test disagrees with the code, decide which of the two encodes the
  intent BEFORE editing either. Here the split was deliberate and already
  recorded in AGENT_LESSONS: the durable latch exists so the next cycle's
  "reconciliation_in_progress" sentinel -- which `health_ready()` deliberately
  excuses -- cannot self-heal a runtime that fails every cycle. Removing the
  latch to satisfy the test would have reintroduced exactly that bug.
- The fix is to pin the real path, not to relax the assertion: raise, then
  `_enter_degraded`, then assert the latch and `health_ready()`. That keeps the
  guarantee AND documents why it is two steps.
- Half a contract is a trap in either direction. Asserting the mid-cycle state
  alone would pass under an implementation that never degrades at all.

## Normalise the JOIN KEY at the boundary, not at the lookup that misses

`ExecutionGuard._net_positions` keyed its map on the RAW broker symbol string
while `evaluate` looked the position up under the DECISION's symbol. When the
broker's casing disagreed (`"aapl"` vs `"AAPL"`), `current_pos` came back
`None` and every rule derived from it silently stopped applying. One
`symbol = symbol.upper()` in the netting loop closed it.

The failure was silent in BOTH directions at once, which is what makes it worth
recording:

- BUY: the pyramiding check is guarded by `if current_pos and current_qty > 0`,
  so an ABSENT position skips the check instead of tripping it. The guard
  approved a second BUY on a symbol already held -- it failed OPEN on the one
  rule written to prevent exactly that.
- SELL: the same None hit `if not current_pos` and refused to close a position
  the broker actually held, with a message blaming a short.

Verified by scratch replay of HEAD vs worktree (no tracked file touched):
`BUY OLD: (True, None)` vs `NEW: (False, 'Máximo 1 posição...')`; `SELL OLD:
(False, '...vendida a descoberto (SHORT)...')` vs `NEW: (True, None)`.

- Normalise where the map is BUILT, not where it is read. Fixing only the
  `net_positions.get(symbol)` call would have left the exposure sum iterating
  mixed-case keys and the map still holding two definitions of one position.
- `if current_pos and ...` is a fail-OPEN guard shape. A missing entry and a
  zero position mean different things, and only one of them is safe; a
  membership lookup that can silently miss will pick the unsafe one. Prefer
  asserting membership explicitly where absence must block.
- "The broker always sends uppercase" is an assumption about a THIRD PARTY.
  The same file already normalised symbols two lines away, so the invariant
  existed in the codebase and only the netting loop ignored it. When two
  components normalise the same broker field, grep for the third that does not.
- Pin mixed-case legs as their OWN test (`_net_positions` collapsing `"AAPL"` +
  `"aapl"` into one entry), not only the end-to-end verdict. The end-to-end test
  passes even if netting splits them as long as the lookup happens to hit one;
  only the map-level test proves the position has a single definition.
- Keep an uppercase-only CONTROL alongside the new case. Confirmed here that
  `OLD` and `NEW` produce identical maps and identical BUY verdicts for
  `"AAPL"`, so the fix changes behaviour only on the casing it was meant to.

## Report the unmatched remainder; never invent the missing price

A per-run FIFO matcher over fills (`get_session_analytics`) silently DISCARDED
the `sell_qty` left over when a SELL had no (or not enough) BUY lot in the same
run. No closed trade, no realized P&L, and no trace of the drop -- reported
session P&L under-stated reality with nothing in the payload to explain the gap.

The fix records the leftover per symbol as `anomalies.unmatched_sells` and
deliberately does NOT estimate a cost basis, so `pnl_realized` remains derived
only from genuinely matched lots. The anomaly is the signal; a fabricated price
would be a worse bug than the shortfall it hides.

- "The local view cannot see what the broker knows" is a recurring class here,
  not a one-off: the same root shape produced rows keyed on raw broker symbol
  casing and two broker orders claiming one local row. When a matcher, join or
  netting pass is bounded to one run/session, ask what it does with the part of
  the input it cannot match, and make that an OUTPUT.
- A droppable remainder is the silent-failure shape to grep for: `while ... and
  queue`, then a loop variable reused as the cursor and never read again after
  the loop. The leftover is the whole finding.
- Never convert an unknown cost basis into a number to make a report tidy. The
  unmatched quantity is honest data; a guessed entry price is a fabricated fact
  that later feeds win-rate and profit-factor statistics.
- Include a CONTROL case (fully matched -> `[]`) next to the new anomaly. It
  pins against over-reporting, which is how this fix could later be "improved"
  into noise on every healthy session.
- Proving a NEW anomaly key is non-vacuous does not require reverting tracked
  code: load `git show HEAD:<file>` as a standalone module in scratch and run
  BOTH versions through the same stub scenarios. Printed the HEAD payload key
  set vs the worktree one (`unmatched_sells` absent at HEAD), plus
  `git grep -c <symbol> HEAD` returning 0.

## Two blast radii in `AlpacaPaperWorker`: per-order vs account-wide

`_run` drives `reconcile_once` and catches everything in one handler. Inside it
the steps deliberately differ:

- `_reconcile_active_orders` CATCHES per order. One order whose broker numerics
  cannot be sourced must not stop the others: it keeps its ACTIVE status, writes
  no fabricated 0.
- `_assert_open_orders_known` (worker.py:150) is NOT wrapped and must not be. It
  answers "is the whole open-order book known to us?", and every one of its
  failure modes (unknown order, status/symbol/side/size divergence, two broker
  orders claiming one local row) is account-wide by construction: sizing the
  next order without knowing what is already outstanding is the fail-OPEN.

`reconcile_once` clears only the per-cycle bits (`reconciliation_ready`,
`degraded`, `degraded_reason = "reconciliation_in_progress"`). The DURABLE latch
`has_reconciled` is cleared solely by `_enter_degraded`, i.e. by `_run`'s
handler, so a raise alone is not a signal.

- When a test drives `reconcile_once` directly, a raise leaves `has_reconciled`
  at whatever it was and `health_ready()` STILL True (it excuses the
  in-progress sentinel by design, to stop /health flapping every 3s cycle).
  Asserting `has_reconciled is False` straight after the raise tests a
  behaviour the design forbids -- `test_divergence_leaves_no_verified_picture_
  after_degrading` already pins the split. A new blast-radius test must assert
  the mid-cycle state, then call `_enter_degraded` to reach the latch.
- Non-vacuity for this step without touching tracked files: monkeypatch
  `_assert_open_orders_known` at RUNTIME in a scratch test to neutralise only
  the comparison under test (e.g. rewrite `qty` to the approved size), rerun the
  same scenario. If the divergent book is then snapshotted and the gate opens,
  the assertion is doing real work. Confirmed: neutralising the SELL size check
  gave `snapshot_writes=1, gate=True, has_reconciled=True` on the exact inputs
  the committed test expects to abort.
- Pin both a healthy SIBLING and a healthy CONTROL in an account-wide test. The
  sibling proves the abort is not per-order (it passes its own checks); the
  control proves the assert is not simply raising on everything, which would
  leave the gate permanently shut.

## `broker_portfolio_snapshots` is CURRENT state, not a history

`provider` is the primary key (services/api/models.py:226) and the worker
maintains the table with `insert(...).values(provider="alpaca", ...)` plus
`on_conflict_do_update(index_elements=["provider"])`. It therefore holds exactly
ONE row per provider, overwritten every reconcile.

- Consequence: an `ORDER BY last_reconciled_at ASC LIMIT 1` "oldest row" query
  on this table cannot mean what it looks like -- there is only one row, so the
  ordering is decorative. `get_session_analytics` used it to pick the session's
  opening equity and returned the CURRENT equity for both ends of the session,
  making `equity_initial == equity_final` on every session and putting live
  equity in the denominator of `return_pct`.
- The correct opener is `paper_runs.initial_cash` for the run (`nullable=False`,
  with `ck_paper_run_money` requiring `initial_cash > 0`); the live snapshot
  stays the closer. Before the first reconcile both ends equal the start cash.
- When auditing any "first vs last" report pair in this repo, first check whether
  the table has a time dimension at all. A single-row upsert table read twice
  returns the same answer twice and looks like a plausible number, not an error.
- Proving the fix without reverting tracked code: run the HEAD version of the
  module loaded from scratch against the same stub connection and compare
  payloads. Here the RED evidence was 3 of 4 new tests failing on HEAD, with
  `return_pct` = 1.9184652278177459 (the live-equity denominator) instead of 2.0.
- Lint baseline was proven rather than assumed: `ruff check --stdin-filename
  services/api/analytics.py - < <(git show HEAD:services/api/analytics.py)`
  avoids writing the baseline into the repo (a temp path outside the tree also
  works, but not `$TMPDIR` if it resolves outside an existing directory).
  HEAD carried 13 errors, the worktree file 11 -- the change removed 2
  pre-existing findings and added none.

## Session return is an ACCOUNT figure, not a P&L figure

docs/M4_CORE.md:67 defines `return_pct` as
`(equity final - initial cash) / initial cash * 100`. `get_session_analytics`
computed the numerator from `total_pnl`, which is a DIFFERENT quantity: this
run's matched FIFO realized P&L plus the unrealized P&L of the CURRENT position
book. Those disagree whenever cash moved for a reason the fill walk cannot see:

- an unmatched SELL has no local BUY lot, so its P&L is deliberately not
  realized (it surfaces as `anomalies.unmatched_sells`) and the account's real
  loss disappears from the reported return;
- a lot inherited from an earlier run that opens or closes inside this session;
- fees settling, a deposit, or a dust lot;
- worst case, a real loss on one symbol netted against an unrelated gain on
  another, so a losing session reports as healthy.

The equity difference is the account's own answer and needs none of that
reconciliation. Practical rule for this repo: when a report metric has a
documented definition in docs/M4_CORE.md, treat the table as the contract and
grep the implementation for which internal quantity it actually numerates from
-- `total_pnl` and `equity_final - initial_cash` are easy to confuse because the
denominator was already right.

- The two halves of this defect were found in consecutive cycles and are the
  same bug: the denominator was the live equity (fixed by taking the opener from
  `paper_runs.initial_cash`), then the numerator was a P&L figure. When a metric
  is reported as a single `return_pct`, check BOTH ends of the fraction against
  the documented formula rather than fixing whichever one a failing test exposed.
- Pinning a metric that now depends on two inputs needs a deliberate CONTROL in
  which those inputs AGREE, otherwise the test cannot distinguish "uses the
  right source" from "always uses the other source". Here: a control session
  where equity moved by exactly the matched P&L (2.0% under both formulas) plus
  a flat session (0.0).
- When an earlier test in the same area starts failing because a neighbouring
  fix changed what a fixture means, fix the TEST rather than weakening the new
  behaviour: the old test was pinning the denominator using a snapshot equity
  that made the account and the P&L disagree, so its scenario had to be pinned
  to an agreeing equity, with the disagreement case moved to the new file.
- Non-vacuity without touching tracked code, second form of this technique:
  `importlib` the HEAD blob written into the scratch dir, then monkeypatch the
  name the test module imported (`t.get_session_analytics = head_mod
  .get_session_analytics`) and call the test functions directly. Result: 3 of 5
  red on HEAD, the 2 controls green.
- `services/api/observer_source.py:156` reads `return_pct` from the ACCEPTED
  BACKTEST report metrics (services/backtesting), not from session analytics, so
  a change to `get_session_analytics`' `return_pct` does not touch the observer
  contract. Check that distinction before assuming a metric has one consumer.
- Rounding: `return_pct` is emitted as `str(return_pct)` on the raw Decimal, so
  it can carry many decimals. docs/M4_CORE.md:63 says monetary values and
  percentages carry 10 decimal places; several analytics fields are rounded
  (`round(win_rate, 2)` etc.) and this one is not. Not yet decided which is
  right -- do not "fix" it without checking the consumer.

## A defaulted contract field is an UNSET field, not a neutral one

`PaperPortfolio.reconciled` defaults to `True`
(`packages/contracts/paper.py:106`). `get_broker_portfolio` derived `degraded`
from the snapshot status but never passed `reconciled`, so every DEGRADED/STALE
book was published as `"reconciled": true` beside `"degraded": true` -- a book
whose last reconciliation FAILED asserting it had been verified against the
broker. Because `True` is the default it is also the value seen in normal
operation, so no reader of the field had a reason to distrust it.

Reusable rules:

- When a constructor omits a field, check the CONTRACT's default before assuming
  the omission is harmless. A `bool = True` default is not "unmentioned"; it is a
  positive claim the route is making on every request it does not think about.
- Two flags about ONE fact should be derived from ONE source. Here both come
  from the stored snapshot status, so they can never disagree; a future edit that
  recomputes either from a second source breaks that by construction.
- Fail-closed means the UNAVAILABLE claim must not be the default. An
  availability-shaped flag (`reconciled`) defaulting to the permissive value
  fails open even while a separate `degraded` flag fails closed.
- Pin the CONTROL when a fix inverts a flag: `test_reconciled_is_true_only_for_a
  reconciled_snapshot` exists so "always report False" cannot pass.

Proving non-vacuity without touching tracked code, third form of this technique:
`git show HEAD:services/api/broker_routes.py | grep -n reconciled` returns only
`last_reconciled_at` hits and NO `reconciled=` kwarg, which is direct evidence
the field was never supplied on HEAD. Read-only, no restore needed.

Latch reachability: `broker_portfolio_snapshots.status` is only ever written
`ACTIVE` (both `_save_broker_snapshot` call sites: worker.py:151
`reconcile_once`, worker.py:587 `_snapshot_broker_portfolio`) or `DEGRADED`
(`_enter_degraded`, worker.py:329). `STALE` appears in the route's membership
test defensively and is never written. So inverting on that set covers every
reachable value, and no third status can slip through as "reconciled".
