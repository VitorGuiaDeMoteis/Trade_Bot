# Momentum Experiment V1.3 — Frozen Protocol

## Scope and isolation

This is a research-only experiment. It does not import the Paper V1 runtime, use a runtime database, submit broker orders, or call Alpaca Trading/LIVE endpoints. Yahoo adjusted history is primary; Alpaca Historical Market Data is cross-check only; FRED DTB3 is the canonical cash and risk-free source. Observations on or after 2026-01-01 are forbidden.

## Universe and periods

- Universe: SPY, EFA, EEM, TLT, GLD, DBC, VNQ.
- Raw history begins 2006-02-06. The first valid signal is 2007-02-28.
- Development: 2007-03-01 through 2016-12-31.
- Burned diagnostic period: 2017-01-01 through 2020-12-31. It may not be used to change parameters.
- Final holdout: 2021-01-01 through 2025-12-31.

Missing lookback history is an error, not a cash signal. Market-session calendars come from the primary price data; FRED is aligned to those sessions without inventing market sessions.

## Strategies and benchmarks

AM Primary uses 12-month total return with no skip. An asset is eligible only when its return exceeds the compounded canonical T-bill return over the same endpoints. Eligible assets are equal weighted; residual capital earns the canonical T-bill return.

RAM Primary applies the same filter, ranks eligible assets by 12-month return, and assigns three 1/3 slots to the top K=3. Unused slots stay in cash.

- B0: 100% canonical T-bill cash.
- B1: monthly equal weight across all seven ETFs.
- B2: monthly 60% SPY / 40% TLT.

Signals are formed after the selected rebalance-session close and execute at the next valid primary-market session open. Primary timing is the last session of each month. Every signal receives data only through its signal date.

## Pre-registered sensitivities

- A1: AM, six-month lookback.
- A2: AM, 12-month lookback, skip the most recent month.
- A3: AM, 12-month return greater than zero instead of greater than T-bill return.
- A4: AM, quarterly rebalance.
- R1: RAM K=2.
- R2: RAM K=4.
- R3: RAM, six-month lookback.
- R4: RAM, skip the most recent month.
- R5: RAM, quarterly rebalance.

Additional frozen robustness checks are 5/10/15 bps round-trip friction, 10/12/14-month AM lookbacks, first/penultimate/last rebalance-session timing, leave-one-out AM, and one-at-a-time common-overlap substitutions for both AM and RAM: SPY→VTI, EFA→VXUS, EEM→IEMG, TLT→VGLT, GLD→IAU, DBC→PDBC, VNQ→SCHH.

## Costs and cash

The quoted 5, 10, or 15 bps is round trip. Each buy or sell side uses `round_trip_bps / 2 / 10000` on absolute traded notional at the next-session open. Cash accrues from the previous market session to the current one using the prior available DTB3 observation and actual calendar days; negative DTB3 prints are floored at zero for the cash account. The identical cash-return series is used by B0 and by Sharpe/Sortino excess returns.

## Metrics

Reported metrics are CAGR, Sharpe, Sortino, positive-magnitude MaxDD, Calmar, annualized volatility, worst 12 months, annual turnover, trades/year, cash percentage, and average positions. Exact zero excess volatility is `ZERO_EXCESS_VOLATILITY`; absent downside volatility is `ZERO_DOWNSIDE_VOLATILITY`; zero drawdown is `ZERO_DRAWDOWN`. CAPM alpha and beta use excess returns.

Monthly regimes are diagnostic only: Bull means SPY above MA200 and positive 12-month return; Bear means SPY below MA200 and negative 12-month return; otherwise Chop. Reports include months, annualized return, Sharpe where defined, positive MaxDD, cash, and exposure.

## Seal and holdout firewall

The source-tree hash canonically hashes normalized relative path and actual bytes for every `research/momentum_v1/**/*.py`, `research/momentum_v1/config.json`, and this protocol. The seal also records the frozen base commit, data hashes, config hash, lock hash, canonical strategy-definition hash, canonical cost-model hash, creation time, and derived protocol seal hash.

The official holdout command recomputes and verifies every sealed input. It refuses an absent/invalid seal and refuses when `HOLDOUT_OPENED` already exists. Once authorized, it writes the marker before evaluating holdout data. There is no override or retry flag.

## Pre-registered decision gates

AM requires all of the following on holdout: Sharpe above B1 by more than 0.15; MaxDD below 70% of B1 MaxDD; Calmar above B1; the same three core comparisons at 10 bps; structurally stable substitutions; no isolated 12-month lookback peak; and at least two A1–A4 variants satisfying the same three core comparisons. Hard stops are AM Sharpe below 0.30, AM MaxDD above 20%, or any leave-one-out Sharpe reduction above 50%.

For deterministic evaluation, substitution instability means a baseline-to-substitution Sharpe sign reversal or substituted AM MaxDD above the registered 20% AM hard stop. An isolated lookback/K peak means the primary Sharpe is strictly greater than both registered neighbors.

RAM is considered only if AM passes. It additionally requires Sharpe above AM by more than 0.10, MaxDD below 130% of AM MaxDD, no isolated K=3 peak versus K=2/K=4, incremental Sharpe when it has incremental turnover, and MaxDD at or below 25%.

- AM and RAM pass: RAM wins.
- AM passes and RAM fails: AM wins.
- AM fails: MOMENTUM — NO EDGE. RAM cannot rescue it.

Only a winning AM or RAM receives the separate $50 replay with $1 minimum notional and six-decimal fractional precision. It never affects winner selection and never sends an order.
