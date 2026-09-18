# Momentum Experiment V1.3 — Implementation Handoff

## Implemented production path

The official `research` CLI exposes `fetch`, `dev`, `diagnostic`, `manifest-preview`, `seal`, `verify-seal`, and `holdout`. The package uses Yahoo adjusted history as primary data, FRED DTB3 for both cash and risk-free returns, and Alpaca Historical Market Data only as a read-only cross-check. Substitution history is stored separately.

The portfolio engine uses primary-market sessions, passes only data through the signal close, and executes at the next valid session open. Round-trip friction is divided equally between entry and exit sides. Missing price/lookback/risk-free history raises instead of becoming cash.

The development and burned diagnostic commands accept only their exact frozen dates. The holdout is reachable only through seal verification, creates `HOLDOUT_OPENED` before evaluation, and has no override or rerun option.

## Sealed inputs

- `research/momentum_v1/**/*.py`
- `research/momentum_v1/config.json`
- `docs/MOMENTUM_EXPERIMENT_V1_3.md`
- Raw primary, FRED, Alpaca cross-check, and Yahoo substitution artifacts
- `uv.lock` as a separately recorded dependency hash
- Canonical strategy and cost definitions

Final result reports are intentionally outside the source-tree hash so the holdout command can write them without invalidating the seal.

## Safety boundary

This implementation does not import or mutate Paper V1 runtime modules, touch `trading_bot_dev`, use a runtime database, submit broker orders, or call Alpaca Trading/LIVE endpoints. The only Alpaca URL in the package is the read-only historical market-data bars endpoint.

## Verification

The research tests use synthetic fixtures for execution, metrics, substitutions, sealing, mutation invalidation, and one-shot holdout behavior. They do not evaluate the real 2021–2025 holdout.
