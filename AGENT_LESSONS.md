# TradingBot Agent Lessons

Durable engineering memory for autonomous development.

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
