# LIVE PAPER

- Execution mode: alpaca_paper explicitly overrides local paper.
- Alpaca Paper executes real API calls to paper-api.alpaca.markets but no real money is used.
- Execution boundary supports BUY (Long only), SELL (Close position).
- Orders use deterministic client_order_id based on risk identity.
