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

None yet.

## Active blockers

None known at initialization.

## Next task

Inspect the repository and select the highest-value small safe improvement.

Do not blindly trust historical TODO or handoff documents when Git HEAD or current runtime evidence contradicts them.

## Autonomous cycle incident

First autonomous cycle interrupted before completion.

What happened:

- A suspected daily-loss circuit-breaker bug was investigated.
- Investigation expanded too far.
- Full-suite pytest baseline consumed excessive time.
- Session context was compressed repeatedly.
- Hermes reached its iteration budget before completing validation.
- Temporary experimental code was left in the worktree.
- The incomplete cycle was manually discarded back to the previous clean commit.

Important:

The suspected daily-equity baseline issue remains UNRESOLVED and must be re-investigated in a future SMALL cycle.

Do not assume the interrupted implementation was correct.

Next investigation should be narrow and should specifically consider whether a daily equity baseline must survive process restarts rather than existing only in RAM.
