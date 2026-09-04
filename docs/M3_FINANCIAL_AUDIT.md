> Atualização de 2026-09-04: a política Bearer de STOP descrita neste registro histórico foi substituída pelo [STOP local sem segredo](M3_STOP.md), com testes e prova física. A auditoria financeira permanece válida.

# Auditoria final M3 — 2026-09-04

**M3 financial/integrity audit: APPROVED**

Escopo: PaperExecutor, contabilidade Decimal, PostgreSQL, pausa, replay e ausência
de trading externo. Não inclui Flutter visual, aceite integral do produto ou M4.

Base confirmada por `git pull --ff-only origin codex/m3-paper` e `git ls-remote`:
`21a467526cf9bc67114bb392a32caef7b3e9f953`. Checkout inicialmente limpo. O primeiro
pull sem argumentos informou ausência de upstream; o pull explícito funcionou.

## Falhas reproduzidas e corrigidas

| Falha no HEAD recebido | Evidência / correção |
| --- | --- |
| Dataset congelado tinha hash, mas a retomada não o conferia | Alteração de volume no JSONB era aceita. Hash, conteúdo válido, vínculos e ordenação agora são conferidos antes de executar. |
| Replay concluído pulava reconciliação; checkpoint fora do dataset era aceito | Cash corrompido após conclusão e `step=999` retornavam sem erro. Inicialização de run existente agora reconcilia, inclusive quando não há trabalho novo. |
| Ordem podia apontar para outro sinal sem a contabilidade perceber | FK válida para outro Signal não mudava o saldo. Conferência agora vincula sinal, risco, candle seguinte, ordem, fill, horário, lado e tamanho ao dataset congelado. |
| Marcas ausentes com carteira zerada passavam | Reconciliação agora exige o conjunto exato de preços/horários do checkpoint, inclusive ativos sem posição. |
| Apenas o último snapshot era validado | Taxa adulterada no primeiro snapshot era ignorada. Todos os snapshots, sua continuidade e suas contas são conferidos. |
| Reset misturava runs arquivados na consulta de decisões | Dois replays retornavam 13 registros para 7 sinais. JOIN agora restringe ao run ativo, em transação REPEATABLE READ, e recusa dados paper inconsistentes com HTTP 503. |
| Controle ativo perdido recriava uma carteira silenciosamente | Remover `system_controls` fazia o replay criar outro run. Existência de runs sem controle ativo agora bloqueia leitura/execução, sem novas escritas. |
| Configuração admitia precisão que PostgreSQL arredonda | Capital com mais de 10 casas e bps com mais de 6 casas eram aceitos. Agora são rejeitados antes da persistência. |
| Intervalos cross-asset sobrepostos expunham fechamento futuro | Deslocar um ativo em 30 minutos era aceito. O replay por lote horário agora rejeita sobreposição entre grupos antes da primeira ordem. Não implementa um novo agendador intrabar. |

As sete regressões iniciais falharam no código recebido; quatro casos adicionais
(controle e três precisões) e a regressão de sobreposição também foram executados
antes da respectiva correção. Relatórios locais ignorados em
`.artifacts/m3-audit-*-before.txt` e `.artifacts/m3-audit-regressions-before.txt`.

O reconciliador independente não chama PaperExecutor, não escreve dados e não
consulta rede. Reconstrói o histórico financeiro, confere fills contra os preços
congelados e compara cada snapshot, resultado, posição e saldo. A função de sizing
do módulo de risco é compartilhada; as operações contábeis são conferidas
independentemente das mutações do executor.

## Invariantes financeiras

Valores monetários: Decimal; armazenamento Numeric(28,10), arredondamento
ROUND_HALF_EVEN a 10 casas. Taxa e slippage: Numeric(16,6), expressos em bps.
Capital padrão: USD 10000; taxa: 1 bps; slippage: 5 bps.

Para quantidade inteira `q`, referência `r`, preço médio `a`, taxa `f` e slippage `s`:

```text
preço BUY  = round10(r × (1 + s / 10000))
preço SELL = round10(r × (1 - s / 10000))
notional   = round10(preço × q)
fee        = round10(notional × f / 10000)
slippage monetário = round10(abs(preço - r) × q)

BUY:  cash novo = cash anterior - notional - fee; average_price = preço
SELL: cash novo = cash anterior + notional - fee
realized P&L bruto da venda = round10((preço SELL - average_price) × q)

market_value = soma(q × marca)
unrealized P&L bruto = soma((marca - average_price) × q)
equity = cash + market_value
equity = initial_cash + realized_bruto + unrealized_bruto - fees
total P&L líquido = equity - initial_cash
total P&L líquido = realized_bruto + unrealized_bruto - fees
```

Slippage já está incorporado ao preço de fill; não é debitado novamente.
Fees são debitadas uma vez por fill e descontadas uma vez do P&L total. As parcelas
realizada/não realizada são **brutas**, não líquidas. Não foram encontrados erros
nas fórmulas existentes de BUY/SELL, preço médio ou dupla cobrança.

Exemplo exato verificado em `test_buy_sell_fee_slippage_and_pnl`: 9 ações,
BUY referência 100 e SELL referência 110. Preços: 100.05 / 109.945;
fees: 0.090045 / 0.0989505; realized bruto: 89.055;
fees totais: 0.1889955; cash/equity final: 10088.8660045;
total líquido: 88.8660045; posição final zerada.

## Matriz de comportamento e persistência

- BUY aprovado sem LONG abre; BUY com LONG não aumenta a posição.
- SELL aprovado fecha todas as ações; SELL sem LONG não gera short nem ordem.
- HOLD e risco REJECTED não chamam o executor nem criam PaperOrder.
- Entrada considera preço com slippage e fee dentro do teto de 10% do equity;
  quantidade inteira, sem margin. Capital insuficiente para uma ação produz ordem
  REJECTED sem fill, sem posição e sem alteração financeira.
- UNIQUE `(run_id, risk_decision_id)` limita a uma ordem por decisão **por run**;
  UNIQUE `paper_fills.order_id` limita um fill por ordem. Reset explícito cria outra
  simulação e preserva o arquivo anterior; a unicidade não é global entre runs.
- Dois executores concorrentes, duas inicializações reais do FastAPI e replay
  repetido não duplicam ordens/fills. Checkpoint, IDs e saldos persistem.
- Ordem, fill, posição, marcas, saldo, snapshot e eventos usam a mesma transação.
  Falhas após fill, posição e snapshot revertem todas as tabelas paper.
- Uma pausa concorrente espera a transação em andamento. Antes do commit, leitores
  só veem o estado anterior. Após a confirmação da pausa, nenhum novo lote executa;
  posições e portfolio continuam legíveis. O lote já em andamento pode concluir
  antes da confirmação, nunca depois dela.
- Replay ordena por abertura UTC e símbolo; usa o OPEN do próximo candle do ativo
  e o sinal do candle anterior fechado. Disponibilidade histórica usa o fechamento
  do candle; atraso maior que uma hora expira o sinal. Todas as aberturas do lote
  ficam disponíveis antes dos fills; fechamentos só após todos os fills.
- Dataset e risco são os congelados no run; mudanças posteriores na fonte não
  reescrevem a simulação. Pausa global continua prevalecendo sobre o risco histórico.
- Corrupção encontrada causa ValueError/código de domínio, rollback e HTTP 503 nas
  consultas financeiras e de decisões. Nenhum saldo vazio substitui a inconsistência.

## Segurança

Busca executada em `services`, `packages`, `scripts`, `tests`, `infrastructure` e
`apps/mobile_app/lib`, pelos padrões `TradingClient`, `submit_order`,
`paper-api.alpaca.markets` e `/v2/orders`: **zero ocorrências de código**.
As menções neste relatório são documentação da busca, não chamadas.

Inspeção do adapter confirmou somente
`https://data.alpaca.markets/v2/stocks/bars` e
`wss://stream.data.alpaca.markets/v2/{feed}`. Alpaca é apenas Market Data.
Testes bloqueiam HTTP/WS externos; não houve smoke externo ou envio de ordens.

POST paper exposto: somente `/api/v1/paper/pause`, com token local obrigatório
(mínimo 32 caracteres), compare_digest e rejeição de Origin de navegador.
Sem token/configuração válida: 401/503. Resume/reset permanecem CLI locais.
API/Compose continuam em loopback. `.env` não é versionado; segredos não foram
exibidos, alterados ou adicionados. Não há credencial de corretora no fluxo paper.

O modelo é local e confia no acesso administrativo ao PostgreSQL e à CLI. Hash
detecta alteração do dataset, mas não é assinatura contra um administrador que
reescreva coordenadamente todo o banco e seus hashes. Não é uma auditoria de
implantação pública ou uma prova formal contra qualquer corrupção possível.

## Gates e evidências

| Comando | Resultado |
| --- | --- |
| `git pull --ff-only origin codex/m3-paper` | Already up to date; base acima confirmada remotamente |
| `docker compose --profile test up -d --wait postgres_test` | Healthy, PostgreSQL 17.9, localhost:5433 |
| `uv run ruff format --check .` | 86 arquivos formatados |
| `uv run ruff check .` | All checks passed |
| `uv run mypy` | Success, 50 source files |
| `RUN_DB_TESTS=1 uv run pytest -q` | 162 passed: 116 unitários + 46 PostgreSQL; 22.72 s |
| `uv run alembic upgrade head; uv run alembic check; uv run alembic current` no banco de teste | No new upgrade operations detected; 0008_m3_paper (head) |
| `git diff --check` | Sem erros |

No PowerShell, definir `$env:RUN_DB_TESTS='1'` antes do pytest. Para Alembic de
teste, usar POSTGRES_HOST=127.0.0.1, POSTGRES_PORT=5433,
POSTGRES_DB=trading_bot_test, POSTGRES_USER=test_only,
POSTGRES_PASSWORD=test_only e MARKET_DATA_PROVIDER=simulator, somente na sessão.

Foram adicionados **16 casos**: 13 de PostgreSQL em `test_paper_audit.py` e 3 de
precisão em `test_paper_engine.py`. Foram reutilizados os testes existentes de
fórmulas, sizing, risco, restart, concorrência e reset. Um aviso de depreciação
Starlette/AnyIO permanece; não foi suprimido e não falhou os gates.

Correções necessárias de gate: removidas três linhas em branco pelo formatter no
contrato Decisions e corrigidos quatro bytes CP1252 em STATUS para UTF-8. Não houve
refactor cosmético, mudança de schema, edição visual Flutter, merge ou M4.

Consulta adicional somente leitura (`SET TRANSACTION READ ONLY`) em
trading_bot_dev:5432: schema atual, **zero runs paper persistidos**. Portanto esta
auditoria aprova a implementação nos cenários reproduzidos no PostgreSQL isolado;
não afirma uma reconciliação de carteira histórica local ou validação no tablet.

Uma consulta reconcilia todo o histórico do run; o custo cresce com o dataset.
A validação cobriu datasets pequenos locais, sem benchmark de escala. Novo agendamento intrabar e métricas M4
não foram implementados. O desenvolvimento foi interrompido ao concluir a auditoria.
