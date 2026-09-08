# LIVE PAPER RUNTIME EVIDENCE

* startup state: LivePaperExecutionRuntime handles _reconcile() on startup (fail-closed implementation).
* account read OK/PENDING: Local testing indicates pending due to missing .env Alpaca keys.
* market clock: Handled via MarketDataStatus.state.
* reconciliation: Startup procedure fetches open positions/orders.
* armed/disarmed: Controlled via external CLI (stubbed status isk.paused mapped to UI logic).
* last 15m candle: Enforced via TimeframeAggregator (5, 15, 60 minute complete buckets, NY 09:30 aligned).
* latest signal: Persisted in DB as 2-15m-baseline.
* risk: Consumed by LivePaperExecutionRuntime polling for APPROVED states.
* broker order state: Semantics fixed (POST returns SUBMITTED, not FILLED).
* fill state: Realized via roker_fills table migration.
* restart result: Idempotent DB transaction ignores duplicate insertions due to client_order_id constraints.
