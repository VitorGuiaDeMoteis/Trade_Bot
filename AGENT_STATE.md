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

## CURRENT BACKLOG (authoritative — read this section, not the history below)

Everything below the `## ARCHIVED` divider is per-cycle narrative kept as evidence.
It is NOT a task list and is NOT verified. This section is the only handoff that
carries authority. Update it in the SAME turn as the commit, and verify every
claim here with a grep or a test run BEFORE writing it (see AGENT_LESSONS.md,
"A backlog claim that is only prose becomes next cycle's false premise").

### Verified CLOSED — do not re-investigate

Each line is pinned by an executable check; a violation now fails a test.

- `broker_order_quantity_divergence` — CLOSED. The account-wide reconcile abort is
  pinned in `tests/test_worker_unknown_order_aborts_whole_cycle.py:354` and
  `tests/test_worker_reconcile_unknown_open_orders.py:222`.
- `broker_open_order_duplicate_for_local_order` — CLOSED. Raised at
  `services/alpaca_paper/worker.py:284`, pinned at
  `tests/test_worker_reconcile_unknown_open_orders.py:269`.
- `broker_portfolio_snapshots.buying_power` NOT NULL at head `f2c8a51d9b10` — CLOSED.
  Pinned by `tests/test_broker_snapshot_not_null_contract.py`. Do not re-audit by
  grep; the test asserts the migration declares `nullable=False`.
- Paper `orders_count_reported=0 while actual>0` symptom — CLOSED as an agent-side
  defect. Registered in `scripts/paper_runtime_parity.py:94` as a known symptom;
  `tests/test_paper_runtime_parity.py:295` pins the registration.
- `health.status=degraded` while `paper.degraded=false, reconciled=true` — CLOSED
  as an agent-side defect and now REGISTERED (this cycle). The runtime ran the
  pre-`health_ready()` `/health`, which read the per-cycle execution gate; the fix
  is `b6b2802`, which is branch-only (runtime is 41 commits behind), so it is
  `explained-by-runtime-lag`. Evidence: 670 of 1138 lines in
  `paper-observations.jsonl` carry it while 1131 have `reconciled: true`.
  Verified this cycle with `./.venv/Scripts/python.exe -m scripts.paper_runtime_parity`
  → `fix b6b2802: explained-by-runtime-lag`. Do NOT re-derive it as a live fault.
- `latest_orders[*].last_reconciled_at: null` — CLOSED as an agent-side defect. The
  nulls are the frozen runtime lagging HEAD (`explained-by-runtime-lag`). Pinned by
  `tests/test_paper_order_reconciled_at_contract.py`, which asserts the single
  production `PaperOrder(` constructor forwards the stamp and that the route uses
  no `outerjoin`.
- The `dict.get(key, 0)` broker-numeric audit — CLOSED across all production
  layers. Re-grepped this cycle: the only remaining hits are
  `services/alpaca_paper/executor.py:38` (no default, raises on missing),
  `services/api/market_store.py:237` (a sequence cursor, not broker numerics), and
  `services/observer/ollama_provider.py:91` (a model-confidence default).
- SIMULATOR portfolio constructor `services/api/paper_queries.py:29` — CLOSED, and
  this was a FALSE PREMISE carried as a live candidate. Read in full this cycle:
  it stamps `reconciled`/`last_reconciled_at` explicitly on both branches
  (lines 43-58), derives `orders_count`/`fills_count` from real SQL `COUNT()`
  (lines 116-129, not from the length of the limited lists), and takes `mode` from
  the run row (line 75) with the CHECK constraint documented inline.

- `smoke_test` rewrote tracked `scripts/evaluation_lab.py` at runtime -- CLOSED
  (this cycle, `193699b`). The harness "capped" a run by rewriting the tracked
  module and leaving a `.bak`; the anchor it patched is gone
  (`evaluation_lab.py:80` already has `n = min(len(candles), 200)`), so the
  rewrite only risked leaving tracked source mangled on a crash. Helpers deleted;
  pinned by `test_smoke_harness_never_rewrites_tracked_production_source` and
  `test_smoke_harness_never_opens_a_broker_provider`.
- The 2 long-standing `smoke_test` failures in `tests/test_alpaca_provider.py` --
  CLOSED (this cycle). Root cause: production `scripts/smoke_test.py` is an
  offline evaluation-lab reporter and has had NO broker seam (`Settings`,
  `AlpacaMarketDataProvider`, `regular_session`) for several commits; only the
  tests were stale. Not a missing seam -- nothing to restore. Replaced by 3
  executable pins; the file is now 66 passed / 0 failed.

### Verified OPEN candidates (ordered; verify before starting)

0. HIGHEST-VALUE, derived and verified this cycle but NOT started (that cycle hit a
   SECOND context compression, so `AGENT_MISSION.md:301-307` forbade beginning the
   edit; recorded here so the derivation is not repeated):
   **Register the notional-BUY `quantity=0` symptom in
   `scripts/paper_runtime_parity.py:KNOWN_FIXES`.**
   - SYMPTOM, as it appears in `.agent-runtime/paper-latest.json`: two filled BUY
     orders carry `latest_orders[*].quantity="0"` while `filled_quantity>0`, yet show
     as fully filled in `latest_fills`. It reads like a broken order-size record; it
     is not.
   - ROOT CAUSE (verified, do not re-derive): notional BUY orders are submitted with
     no share count, so `requested_quantity` is genuinely None and the fill carries
     the real share count. HEAD's `broker_routes.py:140-146` already falls back to
     `filled_quantity` when `requested_quantity` is None; the fix commit is `a05d136`.
   - IT IS RUNTIME LAG, not a live defect. `git merge-base --is-ancestor a05d136
     72d37d8` returns non-zero (runtime LACKS the fix) and
     `git rev-list --count 72d37d8..HEAD` = 59, so the frozen runtime still runs the
     un-fallback behaviour.
   - WHY IT IS WORTH THE EFFORT: `KNOWN_FIXES` already registers the sibling
     symptoms of the same lag (`5ee4f29`, `7252052`, `b6b2802`); this one is NOT
     registered, so it reads as a fresh anomaly forever -- exactly the failure the
     module exists to prevent.
   - TASK: append `KnownFix(commit="a05d136", symptom=...)` naming
     `latest_orders[*].quantity=0`, `filled_quantity>0` and the notional-BUY cause;
     then add a sibling test in `tests/test_paper_runtime_parity.py` modelled on
     `test_health_flap_symptom_is_registered_against_its_own_fix` (assert the sha
     resolves, state is `EXPLAINED_BY_LAG`, symptom is excused and rendered).
   - VERIFY WITH: `./.venv/Scripts/python.exe -m scripts.paper_runtime_parity`
     → expect `fix a05d136: explained-by-runtime-lag`; then
     `./.venv/Scripts/python.exe -m pytest tests/test_paper_runtime_parity.py -q`.
     Read-only both ways; touches no broker state and no runtime database.

1. `RUN_ALPACA_SMOKE_TEST` doc drift (verified by grep this cycle, NOT fixed):
   the flag is documented as the live-smoke opt-in in `.env.example:26`,
   `docs/DEMO.md:144`, `docs/DECISIONS.md:152` (D035), `docs/SECURITY.md:85`,
   `docs/RUNBOOK.md:195,202` and `README.md:126`, but nothing in production reads
   it -- the only code references are `tests/conftest.py:52` (sets it to `0`) and
   `.env.example`. Those docs still promise a broker smoke that cannot run.
   Task: correct them to the offline reporter reality (or restore a real opt-in
   deliberately). `README.md`/`docs/RUNBOOK.md` are written in Portuguese.

## Latest cycle (2026-10-04, RECOVERY MODE -- worktree was DIRTY at start)

- Task: finish the inherited WIP, no new task. The WIP was the previous cycle's
  recorded next candidate: the 2 `smoke_test` failures.
- Confirmed no temporary breakage in the WIP: `git status` showed only
  `scripts/smoke_test.py` + `tests/test_alpaca_provider.py`; no `scripts/*.bak`
  remained and `scripts/evaluation_lab.py` was unmodified (so an earlier crashed
  smoke run had not left tracked source mangled).
- Verified the WIP's central claim before keeping it: the anchor the deleted
  helpers patched (`n = len(candles)`) really is gone from
  `scripts/evaluation_lab.py` -- line 80 now reads
  `n = min(len(candles), 200)`. So `limit_candles()`/`restore_candles()` were
  rewriting a tracked production module to achieve nothing, and a crash between
  the two calls would have left it mangled.
- Also verified the second claim: the production harness has NO broker seam (it
  imports only `json`, `asyncio`, `pathlib`, `collections.Counter`,
  `run_evaluation`). So the 2 old tests were stale, not a regression, and there
  was no seam to restore.
- Fixes I made INSIDE the WIP before committing (lint/hygiene only, no behavior
  change): the WIP's new line `tests/test_alpaca_provider.py:461` tripped the
  repo's own `line-length = 100` (`E501`), so it was wrapped; and its `.bak`
  assertion scanned `Path.cwd()` (the whole repo tree, after
  `monkeypatch.chdir`) -- replaced with `tmp_path.rglob`, which covers the same
  CWD-relative path the deleted helpers used, at bounded cost.
- Validation: `pytest tests/test_alpaca_provider.py -q` -> 66 passed, 0 failed
  (was 2 failed in this file). `ruff check tests/test_alpaca_provider.py` ->
  All checks passed. `mypy scripts/smoke_test.py tests/test_alpaca_provider.py`
  -> Success. `ruff check scripts/smoke_test.py` still reports 2 errors (`I001`
  import order, `E501` on the pre-existing `subdirs = sorted(...)` line): both
  pre-existing at HEAD (HEAD has 4) and part of the 110 errors
  `ruff check scripts/` already reports, so `scripts/` is not lint-gated. Left
  alone to keep this recovery cycle to one task.
- PAPER_REVIEW: observed_at 2026-10-04T11:06:58Z, run ACTIVE,
  `health.status=degraded`, `paper.paused=false`, `paper.degraded=false`,
  `paper.reconciled=true` (last_reconciled_at 2026-10-04T11:06:49Z, fresh);
  positions AAPL/SPY/TSLA (~10 USD each);
  orders_count_reported=0 vs actual=13; fills_count_reported=0 vs actual=11;
  unrealized_pnl=-0.0367 (equity 99951.28, cash 99921.35). market_data
  state=`market_closed`, last_bar_at 2026-10-02T21:00Z, last_message_at
  2026-10-04T03:03:51Z -- a Sunday reading, so `market_closed` is correct. All
  three standing anomalies remain CLOSED as `explained-by-runtime-lag`; no new
  actionable Paper finding. (Read for context only; this cycle began DIRTY, so
  the mandatory clean-cycle gate does not apply.)
- Next candidate: the `RUN_ALPACA_SMOKE_TEST` doc drift above (one coherent docs
  task).

## Cycle 2026-10-04 (RECOVERY MODE -- worktree DIRTY again at start; doc-only WIP)

- Task: finish the inherited WIP. That WIP was NOT production code -- it was the
  previous cycle's uncommitted `AGENT_STATE.md` + `AGENT_LESSONS.md` bookkeeping
  for code already committed as `193699b`. Confirmed via `git diff --name-only`:
  only the two `.md` files, no `scripts/` or `tests/` change, no temporary
  breakage anywhere.
- Re-verified the WIP's central claims rather than trusting them (they describe
  committed code, but a wrong handoff steers the next cycle): both pin tests
  exist (`tests/test_alpaca_provider.py:421` and `:546`); the anchor the deleted
  helpers patched really is gone (`scripts/evaluation_lab.py:80` is now
  `n = min(len(candles), 200)`); `scripts/smoke_test.py` still imports only
  `json`, `asyncio`, `pathlib`, `Counter`, `run_evaluation` -- so no broker seam
  exists to restore; and no `scripts/*.bak` remains from an earlier crashed run.
- The one real defect was in the WIP itself, not in code: the lessons patch had
  demoted the top-level heading `## An append-only state file rots the section a
  cycle reads FIRST` into an indented continuation of the section above it, so a
  whole durable lesson read as if it were a bullet of "Environment facts". Fixed
  by restoring the `## ` heading and its bullets to column 0. Note the
  `patch` tool CANNOT fix this: it preserves the indentation of the block it
  matched, so an un-indent needs a small script (written to the scratch dir and
  run as a file -- `python -c` is blocked on this host). Added the corollary to
  that same lesson so the next cycle checks `^## ` before committing.
- Validation: `tests/test_alpaca_provider.py` -> 66 passed, 0 failed. The 6 tests
  that parse `AGENT_STATE.md` as a contract
  (`test_guard_in_flight_fail_closed`, `test_daily_loss_equity_missing`,
  `test_broker_snapshot_not_null_contract`, `test_guard_position_aggregation`,
  `test_paper_order_reconciled_at_contract`,
  `test_worker_broker_numeric_fail_closed`) -> 43 passed. `grep -c '^  ## '`
  returns 0 for both files, so no heading is nested anymore.
- Standing environment reminder for the next cycle: pytest only runs with
  `DATABASE_ROLE=test EXECUTION_MODE=local_paper MARKET_DATA_PROVIDER=simulator`
  and the `TradingBot-unified/.venv` interpreter; the bare `python` on PATH has
  no pytest installed.
- PAPER_REVIEW: not re-read this cycle -- the observation was ~1h old at the
  previous cycle and this cycle began DIRTY, so the clean-cycle gate does not
  apply. Next CLEAN cycle must read `.agent-runtime/paper-latest.json` and emit
  the mandatory `PAPER_REVIEW:` line before picking the backlog task.
- Next candidate: still the `RUN_ALPACA_SMOKE_TEST` doc drift (candidate 1 in
  the authoritative backlog above).

## Previous latest cycle (2026-10-04, RECOVERY MODE -- worktree was DIRTY at start)

- Task: finish the inherited WIP. The WIP was the previous cycle's recorded next
  candidate: pin the `market_data` staleness verdict so Mission Control can tell
  "feed died" from "no new bar yet".
- First verification result, which changes the framing: the verdict is NOT
  missing. Production already implements it in two places --
  `services/market_data/alpaca_provider.py:326-346` (`get_status` returns
  `market_closed` when the session is shut, `delayed` when the session is open
  past 2h and `last_bar_at` is older than 2h or absent) and
  `services/api/main.py:177` (`ready = ... state in {"connected",
  "market_closed"}`, so `delayed` correctly yields 503/degraded). So this was a
  MISSING-TEST defect, not a missing-code defect, and no production change was
  warranted. The AGENT_STATE candidate text said staleness "has no distinct
  verdict"; that was a false premise, now closed.
- WIP as inherited (test-only, 2 files, +91/-2):
  `tests/test_alpaca_provider.py` tightened
  `test_auth_and_subscription_acknowledged` from an unfalsifiable
  `state == "connected" or state == "delayed"` to the single exact verdict
  `== "delayed"`, and added two staleness tests (mid-session silent feed is
  `delayed` not `market_closed`; outside the session / first 2h the same stale
  bar must stay silent). `tests/test_health.py` added a parametrized
  ready-set test pinning `connected`/`market_closed` -> 200 ok and
  `delayed`/`stalled`/`reconnecting` -> 503 degraded.
- Defect found IN the WIP and fixed before committing:
  `test_health_verdict_covers_market_data_states` introduced one NEW mypy
  error -- `client.app.state.simulator.provider` in the `patch.object` target
  had no `# type: ignore` while the adjacent `.simulator.state` line did
  (`Callable[...] has no attribute "state"`). Fixed with the same inline
  ignore, matching the file's existing convention.
- Confirmed the new health test reaches the real `/health` producer and cannot
  pass incidentally: `SimulatorRuntime.status`
  (`services/api/simulator_runtime.py:57-67`) only copies the provider's state
  when the runtime state is `connected` (the test sets it), and its
  `stalled` override is gated on `status.provider == "simulator"` while the
  stub reports `alpaca`, so the pinned verdicts are genuinely the
  `main.py:177` set membership.
- Validation: `pytest tests/test_alpaca_provider.py tests/test_health.py -q`
  -> 85 passed, 2 failed; both failures are the documented pre-existing
  `smoke_test` ones (`scripts/smoke_test.py` has no `Settings` attribute, see
  AGENT_STATE.md:1667), untouched by this WIP. The 8 WIP-relevant nodes
  (3 provider + 5 parametrized health cases) pass individually.
  `ruff check` both files -> All checks passed. `mypy` both files -> the WIP's
  error is gone; only the 2 pre-existing `test_alpaca_provider.py:427/499`
  `no-untyped-call` errors on `smoke_test.main` remain (same pre-existing
  class as the 2 test failures).
- PAPER_REVIEW: run ACTIVE, `health.status=degraded`, `paper.paused=false`,
  `paper.degraded=false`, `paper.reconciled=true` (last_reconciled_at
  2026-10-04T10:45:31Z, fresh); positions AAPL/SPY/TSLA (all micro, ~$10);
  orders_count_reported=0 vs actual=13; fills_count_reported=0 vs actual=11;
  unrealized_pnl=-0.0367 (equity 99951.28, cash 99921.35). market_data
  state=`market_closed`, last_bar_at=2026-10-02T21:00Z / last_persisted_at
  2026-10-02T21:01:55Z vs last_message_at=2026-10-04T03:03:51Z. This is a
  Sunday 10:45Z reading, so `market_closed` is CORRECT and the two-day-old bar
  is expected, not a stall -- the very distinction this cycle's tests pin.
  All three standing anomalies (degraded-with-reconciled, 0-vs-13/11 counts,
  `last_reconciled_at: null` on orders) remain registered CLOSED as
  `explained-by-runtime-lag`; no new actionable Paper finding.
- Next candidate: the two `smoke_test` failures are now blocking a fully green
  `tests/test_alpaca_provider.py` for several cycles running, so promoting
  them from "known environmental" to a real task is worth it: verify whether
  `scripts/smoke_test.py` was refactored to drop its `Settings` import while
  the tests still monkeypatch it, and either restore the seam or update the
  tests. Confirm first that the target behavior is not intentionally gone.

### Previous latest cycle (2026-10-04, RECOVERY MODE — worktree was DIRTY at start)

- Task: finish the inherited WIP, do not choose new work.
- WIP found uncommitted: `scripts/paper_runtime_parity.py` +
  `tests/test_paper_runtime_parity.py` taught the parity gate to classify the
  latest observation (`read_observation` / `ObservationHealth`: ok,
  observer-error, incomplete, missing, unreadable, not-examined) so a
  `paper-latest.json` stub is never rendered as a healthy runtime.
- Defect found IN the WIP and fixed before committing:
  `test_an_unusable_runtime_still_prints_the_observation_verdict` patched
  `parity.subprocess_run_git`, but `build_report` binds that callable as an
  import-time default argument, so the patch never reached it. The test passed
  because REAL git fails on the placeholder path `C:/frozen/runtime`, i.e. for
  an environmental reason, leaving the new `except (RuntimeError, OSError)`
  branch unexercised. Now routed through a new `_use_git(monkeypatch, git)`
  seam (the only one `main` actually goes through) and the test asserts the
  INJECTED error text, so it can no longer pass on the wrong evidence.
- Validation: `pytest tests/test_paper_runtime_parity.py -q` -> 35 passed;
  `ruff check` on both files -> All checks passed; `mypy
  scripts/paper_runtime_parity.py` -> Success. Real read-only run
  (`python -m scripts.paper_runtime_parity`, exit 0) prints
  `observation : ok (2026-10-04T10:28:21.992131+00:00)`.
- PAPER_REVIEW: run ACTIVE, health degraded, paper.paused=false,
  paper.degraded=false, paper.reconciled=true (last_reconciled_at
  2026-10-04T10:28:08Z, fresh); positions AAPL/SPY/TSLA;
  orders_count_reported=0 vs actual=13; fills_count_reported=0 vs actual=11;
  unrealized_pnl=-0.0367 (equity 99951.28). Observation verdict: `ok` — a real
  `paper` payload, no `observer_error` stub. All three anomalies
  (degraded-with-reconciled, count mismatch, `last_reconciled_at: null` on all
  10 orders) are already registered CLOSED as `explained-by-runtime-lag`; no
  new actionable finding this cycle.
- Follow-on closed while verifying: the previous cycle's "next candidate"
  (positional `KNOWN_FIXES[0]` ancestry anchor) is ALREADY FIXED — `_behind_report`
  at `tests/test_paper_runtime_parity.py:261-276` enumerates the whole registry
  (`ancestors |= {(fix.commit, BRANCH_HEAD) for fix in KNOWN_FIXES}`). Do not
  re-open it.
- Next candidate: the `health.market_data` staleness verdict above.

### Previous latest cycle (2026-10-04, worktree was clean at start)

- Task: register the `/health` execution-gate flap as a parity-known symptom, and
  make the parity test survive registry growth.
- Change: `KNOWN_FIXES` gained `b6b2802` in `scripts/paper_runtime_parity.py`.
  Evidence: 670 of 1138 lines in `paper-observations.jsonl` carry
  `health.status=degraded` while 1131 carry `reconciled: true`; the runtime
  (frozen at 76813fd) predates `health_ready()`, so it publishes degraded from
  the per-cycle execution gate. Now reported as `explained-by-runtime-lag`.
- Follow-on defect found and fixed in the same cycle: `test_every_known_fix_is_classified_independently`
  asserted whole-tuple equality, so it failed the moment a third entry was
  appended. Rewritten to per-entry membership plus a set-identity assertion that
  holds as the registry grows (the trap was "delete the new finding to make the
  test pass").
- Validation: 32 passed (`tests/test_paper_runtime_parity.py`,
  `tests/test_health_paper_worker_ready.py`); ruff and mypy clean on
  `scripts/paper_runtime_parity.py`.
- Next candidate: extend the same identity-over-position treatment to the
  remaining positional fixture (`KNOWN_FIXES[0]` ancestry in `_behind_report`,
  `tests/test_paper_runtime_parity.py:198`) — verify it still classifies every
  entry independently before touching it.

### Working commands this repo (verified on this host)

The `python` on PATH is NOT this repo's interpreter. Use:

    ./.venv/Scripts/python.exe -m pytest <targets> -q
    ./.venv/Scripts/python.exe -m ruff check <targets>
    ./.venv/Scripts/python.exe -m mypy <targets>
    ./.venv/Scripts/python.exe -m scripts.paper_runtime_parity

`python -c` and `execute_code` are BLOCKED in unattended single-query mode on this
host; read JSON evidence with read_file / search_files instead.

## ARCHIVED (per-cycle narrative — evidence only, not a task list)

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

SUPERSEDED — do not pick a task from this section. It was frozen at this line
while ~1500 lines of per-cycle notes were appended below it, which is how three
false premises survived. The authoritative list is the CURRENT BACKLOG section at
the top of this file. Everything stated here was re-verified on 2026-10-04 and
resolved to CLOSED; the text is kept only as a record of what was once believed.

The three most recent cycles all ran in RECOVERY MODE
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

================================================================================
CYCLE 2026-10-04 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The tree was dirty (`M services/api/paper_queries.py`,
`M AGENT_LESSONS.md`, `?? tests/test_paper_portfolio_reconciled.py`), so per the
recovery rule this cycle only reviewed, validated and committed that unfinished
work -- exactly the "next candidate task" recorded at the end of the prior state
file: the SECOND `PaperPortfolio` constructor in services/api/paper_queries.py,
built for the simulator/REPLAY path.

REVIEW OF THE WIP: no temporary or intentionally-broken code present; the change
is two explicit stamps plus focused tests. `PaperPortfolio.reconciled` defaults to
True (packages/contracts/paper.py:106) and the constructor never supplied it, so
BOTH return paths published the contract default. The no-active-run path was
genuinely wrong: it returned a book that is nothing but the configured opening
balance and published it as `"reconciled": true`. The active-run path was
"accidentally right" -- the default happened to equal the truth -- which is
indistinguishable in the payload from the broken case next to it. The fix stamps
both fields on every return path (`reconciled=False`/no stamp with no active run,
`reconciled=True`/stamp after `store.reconcile` rebuilt the book), which makes a
third UNSET outcome structurally impossible. This is the sibling of the
broker-route defect fixed in fbdbac1 one commit earlier.

CHANGES (already made by the interrupted cycle; verified, NOT rewritten -- no
production code was edited by this cycle):
- services/api/paper_queries.py: added `from datetime import UTC, datetime`, the
  two fail-closed stamps, and comments explaining why a defaulted contract field
  is an unset one.
- tests/test_paper_portfolio_reconciled.py (new, 4 tests): no-active-run is never
  reconciled; absent control row is never reconciled; active-run still reports
  reconciled=True WITH a tz-aware stamp (the control, so a blanket
  `reconciled = False` would fail); and a mechanism guard asserting
  `PaperPortfolio.model_fields[...]` defaults plus flag/stamp agreement on both
  paths.
- AGENT_LESSONS.md: the reusable entry for this defect class and the harness trap.

VALIDATION (re-run independently, not taken on trust):
- 4 passed in 0.10s for tests/test_paper_portfolio_reconciled.py.
- 32 passed in 0.44s for the three-file regression set (test_paper_portfolio_reconciled,
  test_paper_portfolio_mode, test_broker_portfolio_counts) -- the sibling tests
  that build the same payload through the other two constructors.
- `ruff check` clean on both changed files; `mypy services/api/paper_queries.py`
  clean (no issues in 1 source file).
- Non-vacuity proven WITHOUT editing any tracked file: `git show HEAD:services/api/paper_queries.py
  | grep reconciled` returns NO match, i.e. the field was never assigned on HEAD
  and therefore defaulted to True on both paths. Read-only; no bug restore.
- Consumer check: `grep -rn "\.reconciled|reconciled=" services/` finds only the
  two constructors, so no production consumer branches on the flag and no
  downstream contract changes. tests/test_paper_routes.py does not exist (the
  route test file is tests/test_paper_page_mode.py), so it was not in the set.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-04T02:11:59Z): health.status=ok, health.database=up,
market_data.state=market_closed (provider alpaca, last_bar_at 2026-10-02T21:00Z),
paper.status=ACTIVE, paused=false, paper.degraded=false, reconciled=true,
last_reconciled_at=2026-10-04T02:11:57Z. Open position symbols AAPL, SPY, TSLA,
all still micro-sized (AAPL $9.987, SPY $9.993, TSLA $9.953).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `ok` again (it was `degraded` last cycle)
-- the known execution-gate flap, not a new fault. Equity, cash, market_value,
P&L and both totals are IDENTICAL to the last two cycles, so this is still the
documented undeployed pre-fix reading of the counted report (the fix is committed
but the frozen runtime predates it), not new drift. The two newest orders remain
the expected intraday SELL pair for the AAPL and TSLA micro-lots, both ACCEPTED
with filled_quantity 0. No broker/local divergence, no duplicate execution, no
stale reconciliation, no accounting inconsistency. Every `latest_orders[*].
last_reconciled_at` is STILL null while the portfolio-level field is populated --
that long-standing candidate task remains open. Nothing here justifies overriding
the recovery-mode work.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in SEVEN consecutive Paper samples. The
portfolio-level constructor work is now exhausted (all three sites derive the flag
explicitly), so the remaining suspect is the ORDER payload: `PaperOrder`
(packages/contracts/paper.py:47) also defaults `last_reconciled_at` to None, and
paper_queries.py:98 builds orders with `PaperOrder.model_validate(dict(r))` from
the `paper_orders` table, which (per services/api/models.py) has NO
`last_reconciled_at` column -- only `broker_orders` does (models.py:262). So the
REPLAY/simulator payload cannot stamp it from the row at all; broker_routes.py:152
is the route that joins it. Determine which payload the frozen observation actually
reads before changing anything, and do not add a column/migration without
justification.

================================================================================
CYCLE 2026-10-04 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The tree was dirty (`M services/api/broker_routes.py`,
`M tests/test_broker_routes.py`), so per the recovery rule this cycle only
reviewed, validated, repaired and committed that unfinished work: the broker
route coerced a NULL `broker_orders.broker_order_id` to an empty string.

REVIEW OF THE WIP: no temporary or intentionally-broken code present. The
production change is ONE constructor argument; the payload fabricated a broker
id that did not exist. `broker_orders.broker_order_id` is `nullable=True`
(models.py:257) and NULL until the broker acknowledges the order -- legitimately
NULL forever for a submission the broker never accepted. `or ""` published
`"broker_order_id": ""`, so any `is not None` check read an unacknowledged order
as genuinely issued, and the route disagreed with the REPLAY constructor, which
reports the contract default None for the same field. Same class as the
`quantity: 0` coercion already fixed in that constructor.

REPAIR MADE BY THIS CYCLE (the only edit): the WIP regression test's fixture
inserted `paper_orders.status="SUBMITTED"`, which is not a member of
`ck_paper_orders_state_m7`, so the test failed with a psycopg CheckViolation
BEFORE reaching its assertion -- it could never have passed. Changed to
`SUBMITTING`, the status the executor actually persists as intent
(services/alpaca_paper/executor.py:138, "Persistir intent"), which is the last
state before the broker replies and so the honest fixture for this scenario.
Production code was NOT edited by this cycle beyond what the WIP already had.

VALIDATION (re-run independently, not taken on trust):
- 4 passed in 1.26s for tests/test_broker_routes.py (3 pre-existing + the 1 new
  regression test), after the repair.
- 36 passed in 1.36s for the four-file regression set (test_broker_routes,
  test_broker_portfolio_counts, test_paper_portfolio_reconciled,
  test_paper_portfolio_mode) -- the siblings that build the same payload through
  the other constructors.
- `mypy services/api/broker_routes.py` clean (no issues in 1 source file).
- Lint baseline proven, not assumed: HEAD's test file reports 7 ruff errors via
  `git show HEAD:... | ruff check --stdin-filename`, the worktree file reports
  the SAME 7 -- the added test introduced none. The I001/F401/E501 findings are
  pre-existing; not fixed here (out of scope).
- Non-vacuity proven WITHOUT editing any tracked file:
  `git show HEAD:services/api/broker_routes.py | grep -n broker_order_id`
  returns `broker_order_id=o["broker_order_id"] or "",` -- direct evidence the
  coercion existed on HEAD. Read-only; no bug restore performed.
- Consumer check: `grep broker_order_id services/` finds only executor,
  worker, models, this route, and mission-control.html:104, which renders
  `r.broker_order_id||r.order_id` (a falsy test, so None and "" render
  identically). No production consumer branches on the None-vs-"" distinction
  yet, so the fix has no downstream contract effect -- the payload is still the
  contract the observer reads.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-04T03:42:12Z): health.status=degraded, health.database=up,
market_data.state=market_closed (provider alpaca, last_bar_at 2026-10-02T21:00Z),
paper.status=ACTIVE, paused=false, paper.degraded=false, reconciled=true,
last_reconciled_at=2026-10-04T03:42:01Z. Open position symbols AAPL, SPY, TSLA,
all still micro-sized (AAPL $9.987, SPY $9.993, TSLA $9.953).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `degraded` again (it was `ok` last
cycle) -- the known execution-gate flap, not a new fault. Equity, cash,
market_value, P&L and BOTH totals are IDENTICAL to the last three cycles, so
this is still the documented undeployed pre-fix reading of the counted report
(the fix is committed but the frozen runtime predates it), not new drift. The
two newest orders are the intraday SELL pair for the AAPL and TSLA micro-lots,
both ACCEPTED with filled_quantity 0E-10, freshly requested at 03:42:07/03:42:08Z
-- a resubmission cadence worth watching, but the total is still 13 and no
duplicate execution or divergence is visible. No broker/local divergence, no
accounting inconsistency, no stale reconciliation. Every `latest_orders[*].
last_reconciled_at` is STILL null while the portfolio-level field is populated
-- now EIGHT consecutive samples; that candidate task remains open. Nothing here
justifies overriding the recovery-mode work.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in EIGHT consecutive Paper samples. The
portfolio-level constructor work is exhausted (all three sites derive the flag
explicitly), so the remaining suspect is the ORDER payload: `PaperOrder`
(packages/contracts/paper.py:47) also defaults `last_reconciled_at` to None, and
paper_queries.py:98 builds orders with `PaperOrder.model_validate(dict(r))` from
the `paper_orders` table, which (per services/api/models.py) has NO
`last_reconciled_at` column -- only `broker_orders` does (models.py:262). So the
REPLAY/simulator payload cannot stamp it from the row at all; broker_routes.py:152
is the route that joins it. Determine which payload the frozen observation
actually reads BEFORE changing anything, and do not add a column/migration
without justification.

================================================================================
CYCLE 2026-10-04 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. The tree was dirty (`M services/api/broker_routes.py`,
`M tests/test_broker_portfolio_counts.py`), so per the recovery rule this cycle
only reviewed, completed, validated and committed that unfinished work: the broker
route published the post-trade BALANCE as the run's starting basis.

REVIEW OF THE WIP: no temporary or intentionally-broken code. The production
change was already correct and complete (one guarded `paper_runs.initial_cash`
scalar read keyed on `system_controls.active_run_id`, plus the `None` passthrough).
On HEAD:218 the route passed `initial_cash=Decimal(str(snapshot["cash"]))`, so
`initial_cash == cash` on every payload, and any `equity - initial_cash` was
structurally ZERO -- a book with three open positions and non-zero P&L reported
itself as having opened flat. Premise verified before completing the work:
`paper_runs.initial_cash` is `nullable=False` (services/api/models.py:116) and is
the ONE definition of the concept -- REPLAY reads the same column via
`store.config.initial_cash` (services/api/paper_queries.py:32), which is exactly
the divergence the `or ""` lesson generalises to.

WHAT THIS CYCLE ADDED (the only edits -- test-side, no production change): the WIP
had already extended `_StubConnection` to serve `run_initial_cash`, but had NOT
written a single assertion, so the prepared stub was dead code and the fix was
unpinned. Added the three missing regression tests:
- `test_initial_cash_is_the_run_starting_cash_not_the_post_trade_balance` --
  proves 100000 (run) != 99941.36 (snapshot balance); the distinct values make a
  pass non-vacuous.
- `test_initial_cash_is_null_when_no_run_is_active` -- no active run => NULL
  starting basis, not zero and not the balance; `cash` still reported.
- `test_initial_cash_is_scoped_to_the_active_run_row` -- pins the run predicate.
Also had to widen the stub's `scalar` return annotation from `int` to `Any`
(the WIP already did) and add `run_bind_params`, because the first version of
the scoping assertion FAILED: SQLAlchemy renders the run id as a BIND
PARAMETER (`WHERE paper_runs.run_id = :run_id_1`), so `str(statement)` cannot
prove WHICH run was read. Recorded `statement.compile().params` in the stub
instead. That is a harness trap worth remembering -- see lessons.

VALIDATION (run independently, not taken on trust):
- 39 passed in 1.46s across the four-file sibling set (test_broker_portfolio_counts,
  test_broker_routes, test_paper_portfolio_reconciled, test_paper_portfolio_mode)
  -- the other constructors that build the same contract.
- `mypy services/api/broker_routes.py`: no issues in 1 source file.
- `ruff check` on BOTH touched files: All checks passed (this file is clean on
  HEAD too -- unlike test_broker_routes.py, it has no pre-existing baseline debt).
- Non-vacuity proven WITHOUT editing any tracked file:
  `git show HEAD:services/api/broker_routes.py | grep -n initial_cash` returns
  `initial_cash=Decimal(str(snapshot["cash"])),`. Read-only; no bug restore.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-04T04:11:31Z): health.status=degraded, health.database=up,
market_data.state=market_closed (provider alpaca, feed iex, last_bar_at
2026-10-02T21:00Z, last_message_at 2026-10-04T03:03:51Z),
paper.status=ACTIVE, paused=false, paper.degraded=false, reconciled=true,
last_reconciled_at=2026-10-04T04:11:27Z, run_id=bf39805a. Open position symbols
AAPL, SPY, TSLA, all still micro-sized (AAPL $9.987, SPY $9.993, TSLA $9.953).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: `health.status` is `degraded` again (was `degraded` last
cycle, `ok` the one before) -- the known execution-gate flap, not a new fault.
Equity, cash, market_value, P&L and BOTH totals are IDENTICAL across the last
four cycles, so this is still the documented undeployed pre-fix reading of the
counted report (the fix is committed but the frozen runtime predates it), not
new drift. The two newest orders are the intraday SELL pair for the AAPL and TSLA
micro-lots, both ACCEPTED; total still 13, so no duplicate execution. No
broker/local divergence, no accounting inconsistency, no stale reconciliation.
Every `latest_orders[*].last_reconciled_at` is STILL null while the
portfolio-level field is populated -- now NINE consecutive samples; that
candidate task remains open and unaddressed. Nothing here justifies overriding
the recovery-mode work.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in NINE consecutive Paper samples. The
portfolio-level constructor work is exhausted (all three sites derive the flag
explicitly), so the remaining suspect is the ORDER payload: `PaperOrder`
(packages/contracts/paper.py:47) also defaults `last_reconciled_at` to None, and
paper_queries.py:98 builds orders with `PaperOrder.model_validate(dict(r))` from
the `paper_orders` table, which (per services/api/models.py) has NO
`last_reconciled_at` column -- only `broker_orders` does (models.py:262). So the
REPLAY/simulator payload cannot stamp it from the row at all; broker_routes.py:152
is the route that joins it. Determine which payload the frozen observation actually
reads BEFORE changing anything, and do not add a column/migration without
justification.

================================================================================
CYCLE 2026-10-04 (worktree DIRTY at start -> RECOVERY MODE, work finished & committed)

TASK: none chosen. Tree was dirty with two UNTRACKED files
(`scripts/paper_runtime_parity.py`, `tests/test_paper_runtime_parity.py`) not
mentioned anywhere in AGENT_STATE.md, so this cycle only reviewed, validated and
committed that unfinished work.

WHAT THE WIP WAS: a read-only `scripts/paper_runtime_parity.py` that classifies
the frozen runtime checkout against this branch using git ALONE (rev-parse /
merge-base --is-ancestor / log). It answers the soundness question behind the
Paper review gate: the frozen runtime is a separate worktree pinned to its own
commit and never fast-forwards, so a field populated only on this branch can
legitimately read `null` in an observation. Statuses: in-sync / runtime-behind /
runtime-ahead / diverged / unknown, plus `observations_may_lag` (True only for
behind/diverged). Exit 0 in-sync, 1 not-in-sync, 2 unknown. Never touches the DB,
the broker, or the frozen worktree.

REVIEW: no temporary or intentionally-broken code; both files are coherent and
complete. Nothing was added this cycle beyond state/lessons -- the WIP already
had focused tests (13) that assert all five classifications plus the CLI exit
codes, and `merge-base`/`log` are correctly given the branch repo as cwd so they
cannot silently resolve against the caller's directory (documented in
`_is_ancestor` and pinned by `test_ancestry_probes_run_in_a_repository_not_the_
caller_cwd`).

VALIDATION (run independently):
- `pytest tests/test_paper_runtime_parity.py -q` -> 13 passed in 0.06s.
- `ruff check` on both files -> All checks passed.
- `mypy scripts/paper_runtime_parity.py` -> Success, 1 source file.
- Real read-only run (`python -m scripts.paper_runtime_parity`, exit 1):
  runtime HEAD 76813fd vs branch HEAD 2459c9c -> `runtime-behind`, 29 commits
  only on this branch. It writes nothing and read the runtime worktree only via
  git plumbing.

PAPER_REVIEW (frozen runtime, read-only, this cycle; observed_at
2026-10-04T04:28:38Z): health.status=degraded, health.database=up,
market_data.state=market_closed (provider alpaca, feed iex, last_bar_at
2026-10-02T21:00Z, last_message_at 2026-10-04T03:03:51Z), paper.status=ACTIVE,
paused=false, paper.degraded=false, reconciled=true,
last_reconciled_at=2026-10-04T04:28:34Z, run_id=bf39805a. Open position symbols
AAPL, SPY, TSLA, all still micro-sized (AAPL $9.987, SPY $9.993, TSLA $9.953).
orders_count_reported=0 vs orders_count_actual=13; fills_count_reported=0 vs
fills_count_actual=11. unrealized_pnl=-0.0366820000, equity=99951.28,
cash=99921.35, market_value=29.93.

CHANGE vs last cycle: none material. Equity, cash, market_value, P&L and BOTH
totals are IDENTICAL across five cycles, so this remains the documented
undeployed pre-fix reading -- now independently confirmed by the parity tool,
since `7252052 fix(api): report real order/fill totals in ALPACA PAPER portfolio`
is one of the 29 branch-only commits the frozen runtime has never run. The two
newest orders are the intraday SELL pair for the AAPL/TSLA micro-lots, both
ACCEPTED; total still 13, so no duplicate execution. No broker/local divergence,
no accounting inconsistency, no stale reconciliation. Every
`latest_orders[*].last_reconciled_at` is STILL null while the portfolio-level
field is populated -- TEN consecutive samples; unchanged and still open.

Next candidate task (carried forward, still first): the observation path null
`last_reconciled_at`, now confirmed in TEN consecutive Paper samples. The
portfolio-level constructor work is exhausted (all three sites derive the flag
explicitly), so the remaining suspect is the ORDER payload: `PaperOrder`
(packages/contracts/paper.py:47) also defaults `last_reconciled_at` to None, and
paper_queries.py:98 builds orders with `PaperOrder.model_validate(dict(r))` from
the `paper_orders` table, which (per services/api/models.py) has NO
`last_reconciled_at` column -- only `broker_orders` does (models.py:262). So the
REPLAY/simulator payload cannot stamp it from the row at all; broker_routes.py:152
is the route that joins it. Determine which payload the frozen observation actually
reads BEFORE changing anything, and do not add a column/migration without
justification.

================================================================================
CYCLE 2026-10-04 (RECOVERY MODE)
================================================================================
Worktree was DIRTY at cycle start, so RECOVERY MODE applied and NO new task was
chosen. Existing WIP was coherent and was finished, validated and committed as-is.

TASK (carried over from the interrupted cycle): make broker fill-window selection
deterministic when two fills share a `filled_at`, by ordering on the unique
`broker_fill_id` as the tiebreaker. The WIP diff was already written; this cycle
confirmed the premise, validated it, and recorded findings.

PREMISE CONFIRMED (why the fix is correct, not merely tidy):
- `broker_fill_id` is the PRIMARY KEY of `broker_fills` (services/api/models.py:268).
- `filled_at` is NOT unique, so ordering by it alone leaves window contents
  non-deterministic when two fills share a timestamp.
- The sibling REPLAY fill query already used exactly this tiebreaker
  (`filled_at DESC, fill_id`), which is what makes broker_routes.py the one
  inconsistent site rather than an arbitrary choice.

CHANGES: none authored this cycle beyond the pre-existing WIP --
- services/api/broker_routes.py: fill-window ordering tiebreaker.
- tests/test_broker_portfolio_counts.py: regression coverage for it.
No production file was left temporarily broken at any point.

VALIDATION (re-run this cycle, all green):
- `pytest tests/test_broker_portfolio_counts.py -q` -> 29 passed in 0.41s.
- `pytest tests/test_broker_portfolio_counts.py tests/test_broker_routes.py
   tests/test_paper_portfolio_reconciled.py tests/test_paper_portfolio_mode.py -q`
  -> 40 passed.
- `ruff check` on both changed files -> All checks passed.
- `mypy services/api/broker_routes.py` -> Success.
No full suite was run (correct for a small cycle).

NEW FINDING THIS CYCLE -- deterministic order_id vs moving requested_at
(root cause NOT established; recorded, deliberately not "fixed"):

In `.agent-runtime/paper-observations.jsonl`, order_id
`7ee2294c-8d5a-5e0e-beda-e246a78e4cec` (newest AAPL SELL) occurs on 664 lines.
Across the last four observations the SAME order_id, broker_order_id and
idempotency_key repeat, while `requested_at` advances by ~60s per cycle.

That combination contradicts the write path and must NOT be read as duplicate
execution:
- services/alpaca_paper/worker.py:507 builds
  `order_id = uuid5(run_id, str(risk.decision_id))` -- DETERMINISTIC, so the same
  (run_id, decision_id) always yields the same id across cycles by design.
- worker.py:517 sets `requested_at=datetime.now(UTC)` at submission.
- services/alpaca_paper/executor.py:139 inserts `requested_at` on first insert and
  does NOT update it on conflict; a repeat insert is rejected as a duplicate
  rather than rewriting the timestamp.
- `orders_count_actual` has stayed 13 across every sample, and the prior cycle's
  review already reads "total still 13, so no duplicate execution". There is NO
  evidence of 664 executions.

So a stable order_id carrying a moving requested_at is a READ-path or aggregation
artifact (a join/fan-out, or an observation writer re-emitting the row with a
recomputed timestamp), not a second submission. The open question is which side
moves the timestamp -- the observation writer, or the portfolio query that builds
`latest_orders`. Do not "fix" this by touching `requested_at`, by changing the
uuid5 derivation, or by deduplicating the observation file: each would destroy the
real submission time or the idempotency guarantee the order_id exists to provide.

Next candidate task (NEW, first in line -- supersedes the null
`last_reconciled_at` hunt, which is unchanged but now second):
Locate which code path emits a recurring order_id with a moving requested_at.
Concrete first step: grep the observation writer for where
`latest_orders[*].requested_at` is serialized, and check whether the portfolio
query fans one paper_orders row out across broker_orders/reconciliation rows.
Confirm it is a read artifact BEFORE touching anything.

Second candidate task (carried forward, still open, now ELEVEN samples):
`latest_orders[*].last_reconciled_at` is still null in every Paper sample while the
portfolio-level field is populated. Prior analysis stands: `paper_orders` has no
`last_reconciled_at` column (only `broker_orders` does, models.py:262), so
determine which payload the frozen observation reads before changing anything,
and do not add a column or migration without justification."

===============================================================================
CYCLE 2026-10-04 (worktree CLEAN at start, one small task)

TASK: close the two stale Paper-review leads, then make that closure mechanical.

Both were the SAME defect and both are already fixed on this branch. Frozen
runtime 76813fd maps the order payload at services/api/broker_routes.py:103 with
`requested_at=o["last_reconciled_at"]` and never stamps the order's own
`last_reconciled_at`, so reconciliation advanced `requested_at` while the
deterministic order_id stayed stable, and the field read null. Branch commit
5ee4f29 corrects both, and tests/test_broker_portfolio_counts.py:341-364 pins
them. There was no second submission and no fan-out to find: the previous
cycle's `requested_at`/uuid5/dedup prohibitions were right and remain right.

CHANGES:
- scripts/paper_runtime_parity.py: added KNOWN_FIXES + FixProvenance and the
  `fixes` / `anomalies_explained_by_lag` report fields. For each known fix the
  tool asks git whether the runtime contains it, and reports one of
  explained-by-runtime-lag / live-on-runtime / unknown-fix.
- tests/test_paper_runtime_parity.py: 4 tests covering all three verdicts plus
  the unreadable-runtime path.

VALIDATION: 17 parity tests + 42 parity/broker-portfolio tests pass; ruff check
clean; mypy clean on the script; live run against the frozen runtime prints
`fix 5ee4f29: explained-by-runtime-lag`. The two `ruff format` complaints are in
pre-existing code and were left alone.

Why it matters: the gate could not tell a stale runtime from a live defect, so
each cycle re-investigated the same symptom. The inverse error is the dangerous
one, so the guard fails safe -- an unresolvable sha or an unreadable runtime
reports NO explanation rather than a reassuring one.

Next candidate task (carried forward, unchanged): `get_session_analytics`
reports `anomalies.unmatched_sells` as a bare `[{symbol, quantity}]` list --
give it the same counted, attributed summary the other anomaly keys get, with a
test pinning the count.

Second candidate task (carried forward): reconcile `return_pct` with
docs/M4_CORE.md:67 (`(equity_final - initial_cash) / initial_cash * 100`); it
still numerates from `total_pnl`.

===============================================================================
CYCLE 2026-10-04 (RECOVERY MODE -- worktree was dirty, WIP finished)

TASK: finish the uncommitted provider-scoping fix in `get_session_analytics`.
No new task was chosen, per the dirty-tree rule.

The WIP was coherent and already explained: three of the broker-owned reads in
`services/api/analytics.py` had no `provider` predicate, but
`broker_portfolio_snapshots` is keyed by `provider` (PK, upserted in place --
m7 migration db6f20ef0e19) and `broker_positions` by `(provider, symbol)`.
With the simulator account and the Alpaca paper account both registered, a
session's P&L mixed in the other account's state:
- `MAX(last_reconciled_at)` spanned both, so `ended_at` reported the OTHER
  account's reconciliation time;
- the position aggregate summed both books into `pnl_unrealized`,
  `avg_exposure`/`max_exposure` and `symbols_data`;
- `... LIMIT 1` on the snapshot read returned an ARBITRARY provider's equity
  (no ORDER BY), corrupting `equity_final` and therefore `return_pct`.

I confirmed this is the only unscoped reader in the API: `broker_routes.py:65`
already filters `broker_positions.c.provider == "alpaca"`, and the orders,
fills and risk_decisions reads are scoped by `run_id`.

CHANGES:
- services/api/analytics.py: selects `provider` on the paper_runs row and binds
  it into all three broker-owned reads. The position SQL was also wrapped to
  keep the touched line inside the 100-char limit (the rest of the file's
  E501s are pre-existing and were left alone).
- tests/test_session_analytics_provider_scope.py (new): a stub serving BOTH
  providers that filters only when the statement actually carries
  `provider = :provider`, so dropping the WHERE clause reproduces the mixed
  numbers instead of silently passing; a CONTROL case runs the same stub with
  the other provider to pin that scoping follows the run row.
- tests/test_session_analytics_{equity_initial,return_pct,unmatched_sells}.py:
  paper_runs stub rows now carry `provider` (NOT NULL on the column).

VALIDATION:
- 21 tests matching `-k analytics` pass (incl. the 5 new ones).
- Discrimination proven WITHOUT touching tracked code: `git show HEAD:services/
  api/analytics.py` was written to the scratch dir and driven with the same
  two-provider stub. HEAD returns pnl_unrealized=-130 (20 plus the other
  account's -150), equity_final=8000, return_pct=700, symbols=[AAPL, MSFT] and
  the other account's later reconciliation; the fix returns 20, 1020, 2.00,
  [AAPL] and its own. The test genuinely fails against old behaviour.
- ruff: no new findings (remaining 9 are pre-existing E501/I001/F401 on
  untouched lines). mypy: 2 pre-existing `var-annotated` errors on the
  untouched `fifo_buys` / `rejections` dicts.
- tests/test_alpaca_deepseek.py also calls get_session_analytics but needs
  Postgres (down) -- known environmental class, skipped, not re-investigated.

CORRECTION to the previous cycle's handoff: its "second candidate" -- reconcile
`return_pct` with docs/M4_CORE.md:67 -- is ALREADY DONE (commit df7df33; see the
comment at analytics.py:141-151 and the return_pct comment at line 50). Do not
spend a cycle on it again.

Next candidate task (first in line, carried forward): give
`anomalies.unmatched_sells` the same counted, attributed summary the other
anomaly keys get, with a test pinning the count.

Second candidate task (carried forward): clear the 2 pre-existing mypy
`var-annotated` errors in services/api/analytics.py (`fifo_buys`, `rejections`),
and decide separately whether the file's remaining E501s are worth rewrapping.

## Recovery cycle: real exposure/drawdown metrics in session analytics

Cycle type: RECOVERY. The worktree was dirty at cycle start with an unfinished
change to `services/api/analytics.py` plus an untracked
`tests/test_session_analytics_exposure_and_drawdown.py`. No new task was chosen;
this cycle finished that WIP.

INTENT of the WIP: `max_drawdown` was the literal `"0.00"` and BOTH `avg_exposure`
and `max_exposure` were the CURRENT market value. So every session reported no
drawdown, and an "average" exposure equal to its final instant.

WHY REBUILD A CURVE: `broker_portfolio_snapshots` holds ONE row per provider, so
there is no stored equity/exposure time series to read. The curve is rebuilt from
this run's fills, anchored on the broker's current book and walked BACKWARD (a BUY
added its notional, a SELL removed its own). Anchoring on the book is what lets
lots inherited from a previous run -- no fill in this run, no opening timestamp --
count in every interval instead of vanishing. Marks are fill prices, so both
metrics are measured at fill granularity and do NOT see excursions between fills.

CHANGES:
- services/api/analytics.py: backward exposure walk + time-weighted average and
  peak exposure; realized-equity series and peak-to-trough `max_drawdown` per
  docs/M4_CORE.md:68 (initial capital is the first peak). The three response keys
  now carry real numbers instead of the `market_value`/`"0.00"` placeholders.
  Fills before `start_time` or a zero-length window still fall back to
  `market_value`, and a run with no fills is unaffected.
- FIX to the WIP: the series paired each backward-walk value with its OWN fill
  timestamp. That value is the exposure in force BEFORE that fill, i.e. over the
  interval ENDING at it, so every segment sat one interval late and understated
  the average. Now anchored at the PREVIOUS boundary, with `market_value` as the
  segment after the last fill.
- tests/test_session_analytics_exposure_and_drawdown.py (new, repaired): the
  stubs exposed `.first`/`.fetchall` directly but production calls
  `.mappings().first()`; rewritten with the explicit stub pattern from
  test_session_analytics_provider_scope.py.
- Two of the three originally failing expectations were WRONG, not the code, and
  were corrected after recomputing each scenario by hand: (1) the fixture had a
  BUY at t=60 with an EMPTY book, so the backward walk subtracted a notional the
  book never carried -- now the run holds the lot it bought; (2) buy 100/sell 150
  is +50 and buy 150/sell 50 is -100, so realized P&L is -50.00 and equity runs
  1000 -> 1050 -> 950, not "1000 -> 1050 -> 1000". The drawdown of 100 was right.

VALIDATION:
- 13 tests in the two analytics files pass.
- 40 tests matching `-k "analytics or exposure or drawdown"` pass.
- ruff: no new findings (the 9 remaining in analytics.py are pre-existing E501/I001/
  F401 on untouched lines; the test file's single E501 is on an untouched
  inherited line). mypy: the same 2 pre-existing `var-annotated` errors on the
  untouched `fifo_buys` / `rejections` dicts -- both sites exist at HEAD.
- Discrimination proven WITHOUT touching tracked code: the first pair of failures
  was reproduced against `git show HEAD:services/api/analytics.py` driving the same
  stub. HEAD returns avg_exposure 66.67 where the hand-computed correct value is
  50.00, which is what isolated the off-by-one rather than guessing.

Next candidate task (first in line, carried forward): give
`anomalies.unmatched_sells` the same counted, attributed summary the other
anomaly keys get, with a test pinning the count.

Second candidate task (carried forward): clear the 2 pre-existing mypy
`var-annotated` errors in services/api/analytics.py (`fifo_buys`, `rejections`),
and decide separately whether the file's remaining E501s are worth rewrapping.

Second recovery pass (same cycle, after re-reading the WIP): the diff was
coherent, finished and uncommitted only. Re-verified rather than re-derived:
13 targeted tests and 40 `-k "analytics or exposure or drawdown"` pass; mypy
reports only the 2 pre-existing `var-annotated` errors. Two E501s WERE newly
introduced on WIP lines (the `nxt = ...` ternary and the `equity_series.extend`
generator), now rewrapped, so `analytics.py` is back to exactly HEAD's 9 ruff
findings, all on pre-diff lines (HEAD 157/161/192 -> now 229/233/264). This was
committed; the next cycle starts clean and may pick a backlog task.

### Paper review at the end of this recovery cycle

PAPER_REVIEW: runtime status ACTIVE / paused False / degraded False (paper block)
/ reconciled True, last_reconciled_at 2026-10-04T06:40:41Z; open positions AAPL,
SPY, TSLA; orders_count_reported 0 vs orders_count_actual 13; fills_count_reported
0 vs fills_count_actual 11; unrealized P&L -0.036682 (equity 99951.28, cash
99921.35).

BOTH mismatches are the ALREADY-FIXED, NOT-YET-DEPLOYED items recorded above, and
the one-command diagnostic confirms it rather than a new fault: `observed_at`
06:40:58 is 17s AFTER this sample's own `last_reconciled_at` 06:40:41, and
`health.status=degraded` is paired with a healthy `paper` block -- exactly the
signature of the pre-fix `health_ready()` fail-closed window. `latest_orders` len
10 vs actual 13 is the documented LIMIT-100 list semantics, not a new cap bug. No
broker/local divergence, no stale reconciliation, no duplicate execution, no
accounting inconsistency beyond the known counts. No new Paper work; do not
re-investigate these two.

================================================================================
CYCLE 2026-10-04 (worktree clean -> new task)

PAPER_REVIEW: runtime ACTIVE / paused False / degraded False / reconciled True,
last_reconciled_at 2026-10-04T06:45:00Z; open positions AAPL, SPY, TSLA;
unrealized P&L -0.036682 (equity 99951.28, cash 99921.35); orders_count_reported
0 vs actual 13, fills_count_reported 0 vs actual 11; two fresh `ACCEPTED`
unfilled SELLs (AAPL, TSLA) at 06:44 UTC with the market closed.

BOTH count mismatches and every null `latest_orders[*].last_reconciled_at` are
the ALREADY-FIXED, NOT-YET-DEPLOYED items recorded in prior cycles; the parity
report's KNOWN_FIXES (scripts/paper_runtime_parity.py:81, commit 5ee4f29) claims
the reconcile stamp symptom, so the deployed runtime predates the fix. The two
open SELLs are the expected intraday pair, no duplicate execution, no broker/local
divergence. Paper gate is CLEAN: no new Paper work, do not re-investigate.

TASK: clear the 2 pre-existing mypy `var-annotated` errors in
services/api/analytics.py, which four consecutive cycles had to caveat rather
than fix (second candidate task in the backlog).

The backlog's FIRST-in-line task was REJECTED, not skipped: its premise is false.
"Give `anomalies.unmatched_sells` the same counted, attributed summary the other
anomaly keys get" -- but at analytics.py:298-305 all three anomaly keys
(`api_reconciliation_errors`, `dust_positions`, `unmatched_sells`) are already
bare `[{symbol, quantity}]` lists, and the counted/attributed summaries
(`sig_count`, `dec_count`, `rejections`) are TOP-LEVEL response keys, not anomaly
entries. There is no asymmetry to remove; implementing it as written would have
given the anomalies block three different shapes while claiming to unify it.
Recorded in lessons so the next cycle does not retry it.

CHANGES (1 production file, 2 lines, no behaviour change):
- services/api/analytics.py:74 `fifo_buys: dict[str, list[dict[str, Any]]] = {}`
  -- the real shape is symbol -> list of per-lot dicts holding qty/price/
  timestamp/fee.
- services/api/analytics.py:248 `rejections: dict[str, int] = {}` -- reason -> count.
  `Any` was already imported at line 4, so no import change was needed.

VALIDATION:
- mypy: `Success: no issues found in 1 source file` (was exactly 2
  `var-annotated` errors on lines 74 and 248).
- ruff: 9 findings BEFORE and AFTER, byte-identical -- proven by stashing the WIP
  and re-running against HEAD, not assumed. No new lint introduced.
- pytest: 28 passed across the five `tests/test_session_analytics_*.py` files;
  40 passed, 610 deselected on `-k "analytics or exposure or drawdown"`.
- Diff is 2 insertions / 2 deletions in one file: annotations only, zero
  behaviour change, so no regression surface.

Next candidate task (first in line): `broker_order_quantity_divergence`
(services/alpaca_paper/worker.py:255) has NO pure unit coverage. It belongs to
the fail-closed family (rejecting a broker/local divergence rather than silently
correcting it), and a test can drive it against a stub without touching Postgres
or the broker. Pin what happens when a fill's cumulative `filled_quantity` does
not reconcile against the broker's own order state, so the guard cannot be
silently weakened later.

Second candidate task: `AGENT_STATE.md` is now 2390+ lines and its carried
candidate tasks have already produced one false-premise task; consider moving the
per-cycle narrative into dated sections and keeping a short current-backlog
summary at the top.

--------------------------------------------------------------------------------
CYCLE 2026-10-04 b (RECOVERY MODE: this cycle found the tree dirty)

No Paper review gate was required: the mission gates it on a CLEAN cycle, and
the PAPER_REVIEW line above is from the same date and still current.

Re-validated the carried WIP before committing, in this repo's own `.venv`
(the Hermes shell `python` on PATH is NOT this project's interpreter):
- `.venv/Scripts/python.exe -m mypy services/api/analytics.py` ->
  `Success: no issues found in 1 source file`.
- `.venv/Scripts/python.exe -m pytest tests/test_session_analytics_*.py -q`
  -> 28 passed in 0.17s.
- `.venv/Scripts/python.exe -m ruff check --output-format=concise` -> 9 findings
  (1x I001, 1x F401 `json` unused, 7x E501). None sit on the touched lines 74
  or 248, so the change introduced no lint. `--output-format=concise` is the
  cheap way to prove that: one line per finding with its column, versus the
  default format's per-finding source echo.

Committed the 2-annotation change plus these state/lessons updates. Tree clean.

--------------------------------------------------------------------------------
CYCLE 2026-10-04 c (RECOVERY MODE: this cycle found the tree dirty)

No Paper review gate was run: the mission gates it on a CLEAN cycle, and the
PAPER_REVIEW line from cycle 2026-10-04 (06:45Z, healthy, mismatches already
fixed-but-not-deployed) is same-date and still current.

The dirty tree was ONE untracked file, no tracked modifications:
  ?? tests/test_worker_pending_broker_state_required.py (207 lines, 7 tests)
So this was a continuation, not a half-applied patch: nothing tracked was
modified, nothing was reverted, and no production code needed to change.

WHAT THE WIP WAS: pure unit coverage for the fail-closed guard at
services/alpaca_paper/worker.py:375-376 -- `_process_pending_submits` raises
RuntimeError("broker_state_not_supplied_to_execution") whenever there IS
approved-but-unsubmitted work and the caller passed no broker account/positions.
That guard already existed at HEAD (uncommitted work added only the test), so
this cycle validated and committed it rather than re-deriving it.

VALIDATION (this repo's own `.venv`; the `python` on PATH is NOT this project's
interpreter):
- `.venv/Scripts/python.exe -m pytest tests/test_worker_pending_broker_state_required.py -q`
  -> 7 passed in 0.10s, against unmodified HEAD code.
- `.venv/Scripts/python.exe -m ruff check <that file> --output-format=concise`
  -> All checks passed! (no E501, unlike most files in this repo).
- DISCRIMINATION proven without touching tracked code: a scratch script
  (profile scratch dir, NOT the repo) read worker.py, stripped EXACTLY the two
  guard lines from its own AST-resolved function source, re-exec'd that copy and
  bound it onto the class in memory, then ran pytest IN-PROCESS against the
  patched class. Result: exactly the 2 fail-closed tests failed
  (test_pending_buy_without_account_raises,
  test_pending_sell_without_positions_raises) and the other 5 still passed. So
  the suite pins the guard, not an incidental path.
- Regression scope, the worker/guard family (8 files): 70 passed, 1 failed.
  The single failure is PRE-EXISTING AT HEAD and unrelated to the WIP -- see
  the new first-in-line task below.

NEW FIRST-IN-LINE TASK (was: broker_order_quantity_divergence coverage):
`tests/test_alpaca_worker.py::test_worker_process_pending_submits_idempotency`
fails at HEAD, standalone, with no WIP present:
  assert 0 == 1  -- `adapter_mock.submit_order.call_count` is ZERO, so
  `_process_pending_submits` never submitted the APPROVED decision at all.
  Both workers are opened (degraded=False, reconciliation_ready=True) and given
  account={"equity": "1000"}, positions=[]. This is the same
  `_process_pending_submits` path the newly committed guard sits in, and 0 calls
  means the decision was silently NOT executed rather than double-executed, so
  the idempotency invariant the test names is currently untested-but-unmet.
  NOTE: it may also be an over-strict fixture (the test mocks submit_order and
  may rely on Postgres; it inserts rows via a real engine at
  test_alpaca_worker.py:248-266). Establish WHY nothing submits before assuming
  a worker bug -- this cycle did not chase it.

Second candidate task (carried forward, unchanged):
`broker_order_quantity_divergence` (worker.py:255) still has no pure unit
coverage; same stub-only approach as the guard test just committed.

## Cycle: stale idempotency fixture, and a mis-scoped regression family

RESULT: the first-in-line task is DONE (fixture repair, test-only, committed).
No production code touched.

- Root cause of `assert 0 == 1`: a FIXTURE, not a worker bug, exactly as the
  handoff warned. `test_worker_process_pending_submits_idempotency` supplied
  `account={"equity": "1000"}`. Commit `38b3b57` (daily-loss breaker wired to a
  real equity baseline, confirmed via `git merge-base --is-ancestor da6a90f
  38b3b57`) made `last_equity` REQUIRED, and `ExecutionGuard` fails CLOSED on a
  BUY without it ("baseline last_equity ausente ou invalido"). So the guard
  correctly refused the BUY and submit_order was never called -- the test was
  asserting the dedup while never reaching the submit path.
- Fix: `account = {"equity": "1000", "last_equity": "1000"}`, shared by both
  workers so the fixture cannot drift between the two racers. Equal sides mean a
  0.00 daily delta, i.e. the breaker is satisfied without loosening it. The
  sibling negative test `test_degraded_worker_never_submits_buy` keeps its bare
  `{"equity": "1000"}` ON PURPOSE -- rejection is its assertion -- and
  `tests/test_paper_v1_stabilization.py:103` likewise stays degraded.
- Added an assertion that pins WHY exactly-1 is correct: one APPROVED decision
  must yield exactly one `paper_orders` row keyed by `risk_decision_id`.
  `submit_order.call_count == 1` alone can hold for the wrong reason (e.g. one
  worker doing the work while dedup is deleted); the row count pins the
  deterministic uuid5(run_id, decision_id) intent instead. `== 1`, never `>= 1`.
- Validation: tests/test_alpaca_worker.py 3 passed; ruff clean on the file; the
  worker/guard family (alpaca_worker, alpaca_guard, daily_loss_baseline,
  worker_pending_broker_state_required, paper_v1_stabilization) 41 passed.

CAUTION, recorded because it nearly wasted the cycle: the family sweep also runs
`tests/test_alpaca_deepseek.py`, whose 5 failures (test_worker_calls_execution_guard,
test_worker_snapshot_runs_without_nameerror, test_worker_sell_uses_exact_quantity_and_no_notional,
test_worker_inflight_prevents_pyramiding, test_worker_inflight_double_sell)
look like blast radius but are NOT. Proven pre-existing by stashing ONLY
tests/test_alpaca_worker.py and re-running at HEAD: same 5 failed, 6 passed.
Leave them; do not re-diagnose them as a regression from an unrelated commit.

NEW FIRST-IN-LINE TASK:
`tests/test_alpaca_deepseek.py` -- 5 worker tests fail at HEAD, standalone. The
representative one, `test_worker_calls_execution_guard` (line 99), asserts the
decision flips to REJECTED for pyramiding, but reads `APPROVED` (line 126). Its
DummyAdapter returns `{"equity": "1000"}` with NO `last_equity` -- the SAME stale
fixture class just fixed in test_alpaca_worker.py -- except the assertion is
inverted, so adding `last_equity` will likely flip it the WRONG way (baseline
present => BUY proceeds => still not rejected for pyramiding). Establish first
whether the test's premise (that one AAPL position must be rejected as
pyramiding) ever matched the current guard, or whether the guard's pyramiding
rule was deliberately changed and these 5 tests were left behind. Do NOT bulk-add
`last_equity` to all of them -- one of these may be the intended degraded-path
assertion. Same order-of-operations as this cycle: git-archaeology FIRST, decide
fixture-vs-intent, and confirm any resulting change is test-only.

## Cycle: 2026-10-04 d + e (RECOVERY MODE: cycle d found the tree dirty)

RESULT: the first-in-line task is DONE -- all 5 red tests in
`tests/test_alpaca_deepseek.py` are green and test-only. Cycle d finished the
repair but ran out of turns before committing, so the tree was still dirty at the
start of cycle e; cycle e re-validated the diff independently and committed it.
No production code touched in either cycle.

PAPER_REVIEW (cycle e, read-only): status ACTIVE, paused=false, degraded=false,
reconciled=true, last_reconciled_at=2026-10-04T08:15:54Z (fresh at
observed_at=08:16:01Z), open positions AAPL/SPY/TSLA, unrealized P&L -0.0366820,
orders_count_reported 0 vs orders_count_actual 13, fills_count_reported 0 vs
fills_count_actual 11. Health block says `degraded` only because market_data
`state=market_closed`; paper itself is healthy. The reported-vs-actual count gap
is the KNOWN observability gap already recorded above (see the
`orders_count_reported` notes), not a new anomaly -- no action taken.

WHAT THE WIP WAS: the previous cycle left a partial repair of those 5 failures --
3 tests fixed, 2 (`test_worker_inflight_prevents_pyramiding`,
`test_worker_inflight_double_sell`) still red. I finished the same job rather than
starting anything new.

ROOT CAUSE (one class, three gates -- all fixture, zero worker bugs):
`AlpacaPaperWorker.__init__` sets `degraded=True` / `reconciliation_ready=False`
(services/alpaca_paper/worker.py:57-58) and `_process_pending_submits` returns at
worker.py:343 while that holds, so a fixture that merely constructs a worker reads
ZERO rows. The failure reads `assert 0 == 1`, which looks like "the worker refuses
to submit" -- the opposite of the truth. Three gates must all be open in a unit
test: (1) `worker.degraded = False; worker.reconciliation_ready = True`, as
`reconcile_once` does in production, (2) `account=`/`positions=` passed or
worker.py:375 raises the intentional `broker_state_not_supplied_to_execution`,
(3) `last_equity` present or the Daily Breaker fails the BUY closed before the
pyramiding rule under test.

CHANGES (1 test file, +70/-13):
- Both `test_worker_inflight_*` tests: open the worker, pass broker state, and give
  the BUY path a `last_equity` baseline equal to `equity` (0.00 daily delta, so the
  breaker is satisfied without being loosened). Positions passed are the BROKER's
  (0.03 AAPL for the double-SELL), matching the DummyAdapter's `get_positions` --
  the second SELL is only rejected because the in-flight quantity is no longer
  sellable.
- Split 5 over-long lines this change had introduced, so the file's E501 count
  drops instead of rising.
- Removed, from the earlier WIP: an injected `DummyExecutor` (the worker builds its
  OWN executor from the adapter, so that double asserted nothing) and an
  `assert worker.degraded == False` after `_snapshot_broker_portfolio` -- only
  `reconcile_once` clears `degraded`, so that assertion covered a different method
  than the one named.

VALIDATION (this repo's `.venv`; the `python` on PATH is NOT this interpreter):
- `pytest tests/test_alpaca_deepseek.py -q` -> 11 passed (was 2 failed, 9 passed).
- Worker/guard family (deepseek, alpaca_worker, alpaca_guard, daily_loss_baseline,
  worker_pending_broker_state_required, paper_v1_stabilization) -> 52 passed. Those
  5 tests are the entire delta; nothing else moved.
- ruff on the touched file: 90 findings at HEAD -> 88 now, identical code
  distribution (I001 5, F401 7, F821 2, E501 74). Proven by `git stash push --
  <only this file>` + re-run + `git stash pop`, not assumed.
- RE-VERIFIED INDEPENDENTLY in cycle e with this repo's own
  `./.venv/Scripts/python.exe`: `pytest tests/test_alpaca_deepseek.py -q` -> 11
  passed; the worker/guard family -> 52 passed; `ruff check
  tests/test_alpaca_deepseek.py --output-format=concise` -> 88 errors.

NEW FIRST-IN-LINE TASK:
`broker_order_quantity_divergence` (services/alpaca_paper/worker.py:314) still has
NO pure unit coverage. Same stub-only approach as the guard test committed in
`991647a`: pin that a fill whose cumulative `filled_quantity` does not reconcile
against the broker's own order state raises
`RuntimeError("broker_order_quantity_divergence:...")` instead of silently
correcting it. It is fail-closed financial safety and no existing test touches it.

Second candidate (carried, unchanged): `AGENT_STATE.md` is now ~2600 lines and its
backlog has already produced one false-premise task. Move the per-cycle narrative
into dated sections with a short current-backlog summary at the top.

## Cycle: 2026-10-04 f (RECOVERY MODE: cycle e left the tree dirty)

RESULT: the WIP is DONE and committed. No new task chosen. Cycle e recorded its
own deepseek commit but did not notice that a SECOND, unrelated edit was sitting
in the tree: the parity module had gained a second `KnownFix` entry (for the
Paper count gap fixed in `7252052`) with tests. I re-validated it independently
and committed it. No production trading code touched.

PAPER_REVIEW (cycle f, read-only): status ACTIVE, paused=false, degraded=false,
reconciled=true, last_reconciled_at=2026-10-04T08:28:13Z vs
observed_at=08:28:17Z (fresh, 4s), open positions AAPL/SPY/TSLA, unrealized P&L
-0.0367420, orders_count_reported 0 vs orders_count_actual 13, fills_count_reported
0 vs fills_count_actual 11. Top-level `health.status=degraded` is the
`market_data state=market_closed` artifact already recorded -- paper itself is
healthy. The reported-vs-actual gap is exactly the symptom the uncommitted
`KnownFix` registers, so the observation and the WIP agreed; no new anomaly.

WHAT THE WIP WAS: `scripts/paper_runtime_parity.py` KNOWN_FIXES gained the
`7252052` count entry, and the test fixture `_behind_report` was fixed to anchor
EVERY known fix (not just `KNOWN_FIXES[0]`) as a branch ancestor, plus three new
tests. That fix is load-bearing: a second entry left unanchored classifies as
`unknown-fix`, and the report then EXPLAINS NOTHING for it -- the exact
re-derivation loop the module exists to stop, and the reason the
reported-vs-actual gap kept reappearing in cycle after cycle.

ONE CHANGE I MADE to the WIP: `test_every_known_fix_is_classified_independently`
asserted on `KNOWN_FIXES[1]`, a positional anchor that rots on the next append
and contradicted the WIP's own argument. Replaced with a lookup by the
`7252052` sha, matching the sibling test. Test-only.

VALIDATION (this repo's `./.venv/Scripts/python.exe`; the `python` on PATH is NOT
this interpreter):
- `pytest tests/test_paper_runtime_parity.py -q` -> 20 passed (0.15s).
- `ruff check scripts/paper_runtime_parity.py tests/test_paper_runtime_parity.py
  --output-format=concise` -> All checks passed. Compared against HEAD by
  `git stash push` of only these two files + re-run + `git stash pop`: also
  All checks passed, so the WIP introduced no lint.
- `mypy scripts/paper_runtime_parity.py` -> Success, no issues.

STATE OF THE BACKLOG: the first-in-line task below is now STALE -- it is
unaffected by this cycle and is the correct next pick.

FIRST-IN-LINE TASK:
`broker_order_quantity_divergence` (services/alpaca_paper/worker.py:314) still has
NO pure unit coverage. Same stub-only approach as the guard test committed in
`991647a`: pin that a fill whose cumulative `filled_quantity` does not reconcile
against the broker's own order state raises
`RuntimeError("broker_order_quantity_divergence:...")` instead of silently
correcting it. It is fail-closed financial safety and no existing test touches it.

Second candidate (carried, unchanged): `AGENT_STATE.md` is now ~2650 lines and its
backlog has already produced one false-premise task. Move the per-cycle narrative
into dated sections with a short current-backlog summary at the top.

## Cycle: 2026-10-04 g (RECOVERY MODE: cycle g-1 left the tree dirty)

RESULT: the WIP is DONE and committed. No new task chosen. Test-only commit; zero
production code touched.

PAPER_REVIEW (cycle g, read-only): status ACTIVE, paused=false, degraded=false,
reconciled=true, last_reconciled_at=2026-10-04T08:55:50Z vs observed_at=08:55:53Z
(fresh, 3s), open positions AAPL/SPY/TSLA, unrealized P&L -0.0366820,
orders_count_reported 0 vs orders_count_actual 13, fills_count_reported 0 vs
fills_count_actual 11. Top-level `health.status=degraded` is again only the
`market_data state=market_closed` artifact. `latest_orders[*].last_reconciled_at`
is null on all 10 orders -- and `python -m scripts.paper_runtime_parity` (exit 0)
already classifies exactly that as `explained-by-runtime-lag` under known fix
`5ee4f29`. No new anomaly; the count gap is registered under `7252052`.

WHAT THE WIP WAS: an untracked `tests/test_paper_order_reconciled_at_contract.py`
(7 tests) that closes a FOUR-cycle backlog item. It is not a fix -- it is the
executable form of the investigation that produced three false premises
("find the SECOND `PaperOrder(` constructor", "relax the column", "audit the
SIMULATOR read sites"), all of which were recorded only in prose and therefore
re-derived every cycle.

CHANGES (1 file, +1/-1 on top of the WIP; the WIP itself is 198 lines, new):
- `test_paper_runs_status_cannot_express_a_degraded_run()` gained a `-> None`
  annotation. That was the ONLY finding against the WIP: `mypy` reported
  `no-untyped-def` on line 160 while the file's other six test functions were all
  annotated. Everything else in the WIP verified as written.
- I did NOT re-litigate the WIP's conclusions. Verified cheaply and independently:
  `PaperOrder(` appears at exactly ONE production site (`broker_routes.py:124`),
  it forwards `last_reconciled_at=o["last_reconciled_at"]` (line 167), and the
  join at line 86 is an inner `broker_orders.join(paper_orders, ...)`.

VALIDATION (this repo's `./.venv/Scripts/python.exe`; the `python` on PATH is NOT
this interpreter):
- `pytest tests/test_paper_order_reconciled_at_contract.py -q` -> 7 passed (0.26s).
- Contract family: `+ test_broker_snapshot_not_null_contract.py`,
  `test_paper_page_mode.py`, `test_paper_runtime_parity.py` -> 36 passed (0.54s).
- `ruff check tests/test_paper_order_reconciled_at_contract.py` -> All checks passed.
- `mypy tests/test_paper_order_reconciled_at_contract.py` -> 1 error before the
  annotation (`no-untyped-def`), Success after.

THE REAL FINDING THIS CYCLE: `AGENT_STATE.md` has been STALE SINCE CYCLE f. Six
commits landed after the last state entry (`d069b65`, `5de56d3`, `6d17316`,
`991647a`, `3de07fe`, `12e6321`, `968e9b5`) and none of them wrote one, so the
"first-in-line task" at the end of the file -- "pin
`broker_order_quantity_divergence`; no existing test touches it" -- is now a
THIRD false premise: `5de56d3` already did it, in
`tests/test_worker_unknown_order_aborts_whole_cycle.py` and
`tests/test_worker_reconcile_unknown_open_orders.py`. Two cycles from now, the
natural pick is a task that has been done for a while. This is the concrete cost of
the carried second candidate, and it is now evidenced rather than suspected.

FIRST-IN-LINE TASK (accurate as of this commit):
`broker_order_quantity_divergence` is DONE -- do not pick it. Next real candidate:
reconcile `AGENT_STATE.md` with the 7 commits that landed without a state entry, and
collapse the ~2700-line per-cycle narrative into dated sections with a short
CURRENT BACKLOG at the top, so the next cycle picks from verified ground. Verify
each backlog claim with a grep/pytest before it is recorded, not after.

Second candidate: `python -m scripts.paper_runtime_parity` reports
`explained-by-runtime-lag` for `last_reconciled_at` but the observation file
carries the symptom string only in code. If the deployed runtime is ever promoted
to HEAD, re-run the report BEFORE filing anything from `latest_orders` again.

## Cycle: 2026-10-04 h (CLEAN tree; state-file reconciliation)

RESULT: the first-in-line task from cycle g is DONE. Documentation-only commit;
ZERO production code touched, so no regression risk and no test suite needed.

PAPER_REVIEW (cycle h, read-only): status ACTIVE, paused=false, degraded=false,
reconciled=true, last_reconciled_at=2026-10-04T09:04:51Z vs observed_at=09:04:58Z
(fresh, 7s), open positions AAPL/SPY/TSLA, unrealized P&L -0.0366820,
orders_count_reported 0 vs orders_count_actual 13, fills_count_reported 0 vs
fills_count_actual 11. Top-level `health.status=degraded` remains only the
`market_data state=market_closed` artifact. Both recurring symptoms are already
classified (`7252052` for the count, `5ee4f29` for the runtime lag). No new
anomaly, so no Paper-driven task outranked the state reconciliation.

THE PREMISE I INHERITED WAS WRONG. Cycle g asserted that "six/seven commits landed
after the last state entry and NONE of them wrote one, so the first-in-line task
is a THIRD false premise". `git show --stat` on all seven disproves it: d069b65,
5de56d3, 6d17316, 991647a, 3de07fe, 12e6321 and 968e9b5 EACH touched
AGENT_STATE.md (46-80 lines apiece). State was never missing; it was MISPLACED.

THE ACTUAL DEFECT (structural, and it explains all three prior false premises):
the authoritative "Next task" section sat frozen at line 1071 while every cycle
APPENDED its entry at the end of the file. By cycle g the file was 2747 lines with
~1500 lines of narrative below the only section a cycle reads first. A reader
following the mission ("read the state, pick a task") reads a section that no
commit ever updates, so the backlog rots silently while the file keeps growing.
That is the true mechanism — not a missing entry, not a wrong conclusion.

CHANGES (2 files, both tracked docs; no code):
- Added `## CURRENT BACKLOG (authoritative...)` directly under "Current
  objective", above all narrative: verified-CLOSED items each paired with the
  executable check that pins it, the verified-OPEN list (now empty), the working
  interpreter commands, and an `## ARCHIVED` divider marking everything below as
  evidence rather than a task list.
- Marked the mid-file `## Next task` section SUPERSEDED with a pointer to the top
  section, keeping its text as a record rather than deleting it.

RE-VERIFIED THIS CYCLE (each CLOSED claim checked before it was recorded):
- `broker_order_quantity_divergence` is DONE — 5 hits across
  test_worker_unknown_order_aborts_whole_cycle.py and
  test_worker_reconcile_unknown_open_orders.py. Cycle g was right about this one.
- `broker_open_order_duplicate_for_local_order` raised at worker.py:284, pinned by
  two tests.
- SIMULATOR constructor `paper_queries.py:29` — read the whole file: it is CORRECT.
  This was the long-carried second candidate and it is now closed as a false
  premise (explicit `reconciled`/`last_reconciled_at` on both branches, counts from
  real SQL COUNT() rather than the length of the limited lists, `mode` from the run
  row).
- Re-grepped the whole `dict.get(key, 0)` numeric audit across services/: the only
  survivors are executor.py:38 (no default, raises), market_store.py:237 (a
  sequence cursor) and ollama_provider.py:91 (a model-confidence default). None are
  broker numerics, so the audit really is complete.

VALIDATION: documentation-only. No production or test file was modified, so no
pytest/ruff/mypy run was required or run. The claims carried into CURRENT BACKLOG
were each verified by the greps and file reads cited above rather than copied from
the old prose.

FIRST-IN-LINE TASK (accurate as of this commit): the verified-OPEN list is EMPTY.
The next clean cycle should derive a candidate from fresh Paper evidence or a
targeted grep of a real risk area, and must record the verification command for it
in CURRENT BACKLOG in the same turn as its commit. Do not re-pick any item in the
CLOSED list; each is pinned by a test that will fail if it regresses.

## Cycle: 2026-10-04 i (CLEAN tree; SECOND context compression -> record-and-stop)

- Worktree was CLEAN at start (`git status --porcelain` empty, no stash), so this
  was NOT recovery mode. Paper review gate ran and passed: `status=ACTIVE`,
  `paused=false`, `degraded=false`, `reconciled=true`, `health.status=ok`,
  positions AAPL/SPY/TSLA, `market_data=market_closed` (correct for a Sunday),
  unrealized P&L -0.0366820. The reported-vs-actual count gap and the /health flap
  are the already-registered `7252052` / `b6b2802` symptoms.
- The two full-position SELL orders (`7ee2294c...` AAPL, `8d2bc663...` TSLA) held
  `ACCEPTED`/unfilled across 1013 consecutive observations. NOT a new anomaly: they
  sit in one place because the market is CLOSED, which is the correct verdict for a
  Sunday. No fix warranted.
- NEW FINDING, fully derived and verified, recorded as candidate 0 in CURRENT
  BACKLOG: two filled BUY orders report `latest_orders[*].quantity="0"` while
  `filled_quantity>0`. Root cause is the notional-BUY convention (no share count
  requested), HEAD's `broker_routes.py:140-146` already falls back to
  `filled_quantity`, the fix commit is `a05d136`, and
  `git merge-base --is-ancestor a05d136 72d37d8` proves the frozen runtime lacks it
  (59 commits behind). So it is `explained-by-runtime-lag` -- but it is NOT in
  `KNOWN_FIXES`, unlike its three siblings, which means every future cycle would
  re-derive it from scratch.
- NOT IMPLEMENTED ON PURPOSE. This session hit a SECOND context compression, and
  `AGENT_MISSION.md:301-307` is explicit: on a second compression do not begin new
  implementation work, record findings/state, commit only safe already-validated
  work, and finish the cycle. Writing the one-entry registry change now would be
  exactly the new implementation work that rule forbids, and it is the higher-risk
  choice: a half-finished edit to `KNOWN_FIXES` plus a new parity test is the same
  shape of WIP that forced RECOVERY MODE in the three preceding cycles.
- NO production or test file was modified, so no pytest/ruff/mypy run was required
  or run (the change is documentation-only). No tracked production code was
  touched, so there is no temporary breakage to clear.
- VALIDATION of the facts written into the backlog: the ancestry check, the 59
  commit distance and `broker_routes.py:140-146` were each read directly this
  cycle; nothing here is copied from earlier prose.

FIRST-IN-LINE TASK (unchanged, accurate as of this commit): candidate 0 above --
register the notional-BUY `quantity=0` symptom against `a05d136` in
`scripts/paper_runtime_parity.py:KNOWN_FIXES` and pin it with a sibling test in
`tests/test_paper_runtime_parity.py`. Verify with
`./.venv/Scripts/python.exe -m scripts.paper_runtime_parity` (expect
`fix a05d136: explained-by-runtime-lag`) and
`./.venv/Scripts/python.exe -m pytest tests/test_paper_runtime_parity.py -q`.
Both are read-only. If that cycle compresses twice before finishing, record and
stop again rather than landing a partial edit.
