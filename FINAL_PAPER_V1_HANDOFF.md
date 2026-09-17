# FINAL STABILIZATION PASS — ALPACA PAPER V1

Data: 2026-09-17  
Branch: feat/m8-night-lab

## Estado entregue

O código do Paper V1 foi estabilizado sem executar sessão Paper, enviar ordens,
limpar o banco runtime, aplicar migration no runtime, fazer commit ou push. O banco
trading_bot_dev continua contaminado e as posições atuais da Alpaca continuam
intactas, conforme solicitado.

Paper V1 ainda não deve ser declarado operacionalmente pronto até a migration ser
aplicada, o broker estar zerado, o clean baseline ser confirmado, Gemini aprovar a
aceitação e DeepSeek concluir a auditoria sem blocker.

## 1. Causa raiz

- Testes construíam Settings() e herdavam .env, cujo default era trading_bot_dev.
- A separação TEST/RUNTIME dependia de convenção de nome e não cobria todos os
  criadores de engine, especialmente o Observer.
- Fixtures executavam deletes/truncates e inseriam REPLAY, b_id e fill_1 no banco
  selecionado.
- O worker podia limpar DEGRADED depois de um ciclo parcial e processava submits
  antes de obter a visão completa e atualizada do broker.
- paper_runs aceitava apenas REPLAY mesmo para Alpaca, confundindo estado runtime
  com replay.
- O head esperado do Alembic estava duplicado em SCHEMA_REVISION hardcoded.

## 2. Arquivos alterados nesta estabilização

Configuração/banco:

- .env.example
- .gitignore
- docker-compose.yml
- services/api/config.py
- services/api/database.py
- services/api/observer_database.py
- services/api/models.py
- infrastructure/docker/migrations/versions/f2c8a51d9b10_paper_v1_runtime_mode.py

Runtime Alpaca:

- services/alpaca_paper/adapter.py
- services/alpaca_paper/executor.py
- services/alpaca_paper/guard.py
- services/alpaca_paper/worker.py
- services/alpaca_paper/observation.py
- services/api/main.py
- services/api/broker_routes.py
- packages/contracts/paper.py
- packages/domain/paper.py

Operação/Mission Control:

- scripts/test-safe.sh
- scripts/start_test_db.sh
- scripts/start-alpaca.sh
- scripts/_run_alpaca.py
- scripts/stop-alpaca.sh
- scripts/paper-status.sh
- scripts/paper_ops.py
- scripts/reset-paper-baseline.py
- scripts/clean_baseline.py
- scripts/alpaca_paper_preflight.py
- scripts/start-mission-control.sh
- services/api/static/mission-control.html

Testes:

- tests/conftest.py
- tests/test_paper_v1_stabilization.py
- tests/test_alpaca_worker.py
- tests/test_observer.py

As demais mudanças já existentes na worktree foram preservadas.

## 3. Arquitetura TEST vs RUNTIME

| Modo | APP_ENV | DATABASE_ROLE | banco esperado |
|---|---|---|---|
| Teste | test | test | TEST_POSTGRES_DB, default trading_bot_test |
| Runtime | local | runtime | RUNTIME_POSTGRES_DB, default trading_bot_dev |

Proteções em camadas:

1. Settings recusa combinações cruzadas.
2. create_database_engine repete a validação antes de criar a engine.
3. O primeiro statement de cada conexão confirma current_database().
4. O Observer usa o mesmo criador central de engine.
5. tests/conftest.py define a identidade test antes da coleta e aborta override
   não-test.
6. DATABASE_URL não é fallback e é recusado no pytest.
7. O test DB usa serviço, database, usuário, porta e armazenamento próprios:
   postgres_test, trading_bot_test, test_only, 55432 e tmpfs.
8. O runtime mantém advisory lock PostgreSQL durante toda a sessão.

Mensagem canônica:

    REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE

## 4. Comando oficial de testes

Teste específico:

    ./scripts/test-safe.sh tests/test_alpaca_worker.py

Suíte:

    ./scripts/test-safe.sh

O script sobe postgres_test, espera health, valida current_database(), aplica
alembic upgrade head somente no test DB e executa pytest.

## 5. Startup oficial

Antes do primeiro startup após este patch, com runtime parado:

    APP_ENV=local DATABASE_ROLE=runtime .venv/bin/python -m alembic upgrade head

Startup:

    ./scripts/start-alpaca.sh

O preflight recusa:

- APP_ENV=test ou role/database divergentes;
- PostgreSQL indisponível;
- zero ou múltiplos heads Alembic;
- alembic current diferente do head;
- endpoint diferente de https://paper-api.alpaca.markets/v2;
- baseline ausente ou active run diferente de ALPACA_PAPER;
- outra instância segurando o advisory lock;
- conta Paper inativa;
- posição inválida, short ou símbolo não gerenciado;
- ordem aberta sem vínculo local exato;
- divergência de símbolo, side, status, notional ou quantity;
- qualquer falha de reconciliação ou persistência.

O preflight não libera execução. A instância runtime adquire o lock, repete a
reconciliação e só então muda system_controls.paused para false.

Ordem do worker:

1. fecha o gate;
2. reconcilia ordens locais ativas;
3. relê account e positions do broker;
4. valida todas as open orders;
5. persiste somente snapshot/positions do namespace broker;
6. abre o gate;
7. retira PAUSE após a primeira reconciliação completa;
8. processa decisões.

Qualquer exceção volta a DEGRADED, mantém BUY bloqueada e o loop continua tentando
recuperar.

## 6. Exposição, BUY e SELL

BUY permanece fixo em 10 dólares:

- broker_orders.requested_notional = 10.00;
- broker_orders.requested_quantity = NULL;
- paper_orders.quantity = 0, representação atual de ordem notional;
- filled_quantity é NUMERIC(28,10) e aceita 0.03005596.

SELL:

    available_quantity = broker_position_qty - pending_sell_qty
    quantity = available_quantity
    notional = NULL

O guard recusa short, oversell e pyramiding. Antes de BUY soma market value de
todas as posições do broker e notional integral de BUYs in-flight de qualquer run.
BUY in-flight sem notional conhecido causa recusa. Posição existente do mesmo
símbolo, inclusive dust, causa recusa.

Posições herdadas não geram paper_orders ou positions fictícias. Elas ficam em
broker_positions, entram no cap e aparecem como BROKER STATE.

## 7. Status

    ./scripts/paper-status.sh

Mostra APP_ENV, database, PID/lock, Alembic current/head, PAUSE, active run/mode,
API health, status PAPER, broker positions/exposure/open orders, snapshot local,
idade da reconciliação, divergência broker/local e DEGRADED. Snapshot com mais de
15 segundos é degradado.

## 8. Pause e stop

    ./scripts/stop-alpaca.sh

O script persiste e confirma PAUSE, envia TERM apenas ao PID oficial, espera até 30
segundos, não usa pkill, não força kill, não para Postgres e não toca volumes. O
lifespan também persiste PAUSE antes de cancelar o worker e liberar o lock.

## 9. Clean baseline

Nenhuma limpeza foi executada nesta passada.

Primeiro pare o runtime e deixe a conta Alpaca Paper sem posições e sem ordens.
A ferramenta não fecha posição nem cancela ordem.

Dry run:

    .venv/bin/python scripts/reset-paper-baseline.py --dry-run

Confirm:

    .venv/bin/python scripts/reset-paper-baseline.py --confirm RESET_PAPER_BASELINE

O dry run mostra database, ambiente, current/head, PAUSE, PID/API/lock, contagens
por tabela, broker positions, broker open orders e backup planejado. Não abre
transação de escrita.

O confirm recusa test env, banco não-runtime, schema fora do head, runtime ativo,
lock ocupado, sistema não pausado, posições/ordens abertas ou falha de backup.
Depois do backup, relê o broker antes do primeiro delete.

O backup usa custom-format pg_dump local ou docker compose exec postgres pg_dump.
Não há TRUNCATE CASCADE.

Allowlist, em ordem de FK:

    broker_fills
    broker_orders
    paper_outcomes
    paper_fills
    paper_orders
    broker_positions
    broker_portfolio_snapshots
    positions
    portfolio_snapshots
    paper_marks
    paper_events
    system_controls
    risk_decisions
    signals
    paper_runs

São preservados alembic_version, schema, candles, system events, market archive e
observer audit. A baseline cria paper_runs.mode = ALPACA_PAPER e PAUSED = true,
sem posição/ordem fictícia.

O antigo scripts/clean_baseline.py, que cancelava ordens e fechava posições, foi
desabilitado.

## 10. Mission Control

Broker mode só aceita o banco runtime. O antigo broker isolado foi desabilitado
porque podia apresentar fixture como estado operacional. Os rótulos agora separam:

- BROKER STATE / ALPACA PAPER para positions;
- BROKER STATE + LOCAL/RUNTIME LINK para orders/fills.

Replay continua separado e explícito.

## 11. Testes exatos para Gemini

Provar recusa do runtime antes da coleta:

    POSTGRES_DB=trading_bot_dev DATABASE_ROLE=runtime .venv/bin/python -m pytest --collect-only tests/test_paper_v1_stabilization.py

Esperado: exit não-zero com REFUSING TO RUN TESTS AGAINST RUNTIME DATABASE.

Aceitação estrutural:

    ./scripts/test-safe.sh tests/test_paper_v1_stabilization.py

Aceitação broker/DB:

    ./scripts/test-safe.sh tests/test_alpaca_guard.py tests/test_alpaca_worker.py tests/test_alpaca_executor.py tests/test_alpaca_paper_incident.py tests/test_fractional_db.py tests/test_broker_routes.py tests/test_health.py tests/test_database_integration.py

Suíte:

    ./scripts/test-safe.sh

Após a suíte, somente depois do clean baseline runtime, provar ausência das fixtures:

    APP_ENV=local DATABASE_ROLE=runtime EXECUTION_MODE=alpaca_paper .venv/bin/python -m scripts.paper_ops audit-runtime-fixtures

Esperado: clean true e zero para REPLAY, b_id e fill_1.

| Gate | Prova |
|---|---|
| A/B/C | stabilization + comando de recusa |
| D/E | preflight/head em stabilization |
| F/G/H | worker, guard, stabilization e incident |
| I | incident e fractional_db |
| J | stabilization, executor e worker |
| K/L/M | baseline em stabilization |
| N | isolamento + audit-runtime-fixtures pós-suíte |

## 12. Gates para DeepSeek

1. Nenhum caminho cria engine fora do validator central.
2. Validação ocorre antes de create_engine e current_database é confirmado.
3. Alembic tem um head e nenhuma revision manual duplicada.
4. Preflight/status/reset não chamam POST/DELETE da Alpaca.
5. PAPER_BASE_URL é a única Trading API.
6. Advisory lock cobre runtime e confirm do reset.
7. Nenhuma BUY ocorre antes de reconciliation_ready.
8. Falha DB/constraint/broker mantém DEGRADED e não vira duplicate fill.
9. Open order desconhecida/divergente bloqueia startup.
10. Exposição usa broker positions e BUYs in-flight de todos os runs.
11. BUY notional persiste fractional fill sem truncar.
12. SELL usa exact available quantity e omite notional.
13. Reset só deleta allowlist depois de backup e segunda leitura do broker.
14. Mission Control não mistura broker mode com test/isolated DB.
15. Shutdown persiste PAUSE antes de encerrar worker.

## 13. Verificações feitas

Sem executar testes nem acessar runtime/broker:

- ruff nos arquivos tocados: passou;
- mypy nos caminhos críticos: passou;
- compileall: passou;
- bash -n: passou;
- alembic heads: um head, f2c8a51d9b10;
- collect-only de stabilization: 14 testes coletados.

A suíte não foi executada, conforme o handoff para Gemini.

## 14. Riscos residuais reais

- trading_bot_dev continua contaminado e o broker pode manter AAPL/SPY/TSLA.
- A migration f2c8a51d9b10 não foi aplicada no runtime.
- O startup recusará a baseline antiga REPLAY até o clean baseline.
- O fallback de backup Docker pressupõe o serviço Compose postgres; em instalação
  externa, disponibilize pg_dump compatível.
- Processo não-oficial que ignore advisory lock continua sendo risco; o reset também
  exige PAUSE, ausência de PID/API e broker vazio.
- A suíte e a auditoria ainda podem encontrar incompatibilidades nas mudanças
  preexistentes da worktree.

## DEFINITION OF DONE — PAPER V1

- [x] test DB/runtime DB isolados no código e Compose;
- [x] pytest incapaz de selecionar runtime pelos caminhos suportados;
- [x] schema head automático;
- [x] startup fail-closed;
- [x] reconciliação antes da execução;
- [x] broker exposure protege o cap;
- [x] BUY notional/fractional preservado;
- [x] SELL quantity/notional NULL preservado;
- [x] PAUSE/STOP implementados;
- [x] clean baseline backup-first reproduzível;
- [x] Mission Control distingue broker de local/runtime;
- [ ] migration aplicada no runtime;
- [ ] broker zerado e clean baseline confirmado;
- [ ] suíte Gemini aprovada;
- [ ] auditoria DeepSeek sem blocker.

Paper V1 só deve ser marcado pronto quando os quatro itens operacionais pendentes
estiverem concluídos.
