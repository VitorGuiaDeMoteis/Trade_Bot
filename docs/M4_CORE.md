# M4 — núcleo de backtesting

Implementado em `codex/m4-backtesting`, a partir de
`fc4aee8d20198a8656c5f375ce9e0b16da423614`. Escopo autorizado: núcleo Python,
replay determinístico e relatório JSON. Flutter, gráficos, replay visual, IA,
Trading API e M5 não fazem parte desta entrega. A estratégia não foi otimizada.

## Arquitetura e persistência

- `packages/domain/backtest.py`: dataset imutável, validação, versões e hashes.
- `services/backtesting/source.py`: snapshot dos candles PostgreSQL em transação
  `REPEATABLE READ` e `READ ONLY`; nenhuma escrita no banco.
- `services/backtesting/engine.py`: coordena `BaseStrategy`, `RiskEngine`,
  `entry_quantity`, `PaperBook` e `PaperExecutor` existentes. Somente o executor
  paper altera cash, posições, taxas e P&L. Não há segunda implementação contábil.
- `services/backtesting/artifacts.py`: validação de manifest e publicação atômica
  em arquivo temporário + fsync + replace.
- `scripts/backtest.py`: CLI de congelamento e execução offline.

PostgreSQL continua sendo a origem persistente dos dados de mercado. Cada pesquisa
usa sua própria cópia congelada em JSON, identificada por SHA-256, com candles,
configuração e versões. Resultados não entram nas tabelas da carteira corrente;
nenhuma migração nova é necessária. Identificação explícita `mode: BACKTEST`.
O replay não consulta `.env`, rede, banco, provider nem estado da carteira paper.

Mesma entrada normalizada e mesmas versões geram os mesmos IDs e bytes de saída.
IDs UUID5 derivam do manifest e dos eventos; horários vêm dos candles, nunca do
relógio de execução. O contexto Decimal do cálculo é próprio, com precisão 28 e
arredondamento monetário do paper (10 casas, HALF_EVEN). Versões incompatíveis,
checksum inválido, float JSON, dados duplicados, parciais ou inválidos abortam.
Mudanças semânticas futuras devem incrementar as versões, incluindo a do núcleo
quando alterarem executor, sizing, serialização ou fórmulas de métricas.

Reinício significa reexecutar integralmente o arquivo congelado. Não existe
checkpoint parcial de backtest no banco. Falha não publica relatório parcial;
um relatório anterior no destino permanece até a substituição completa.

## Relógio e ausência de look-ahead básico

1. Aceitar apenas candles fechados de 1h em UTC, com um provider por dataset.
2. Ordenar por `(open_time, symbol)`; rejeitar sobreposição temporal entre grupos,
   inclusive candles de ativos diferentes deslocados em meia hora.
3. Em cada grupo, marcar todos os ativos presentes no OPEN antes de qualquer fill.
4. Avaliar risco do sinal anterior do próprio ativo no OPEN atual. Sinal gerado
   depois desse instante é erro; sinal vencido é rejeitado pelo risco existente.
5. Executar ao OPEN atual com slippage, em desempate alfabético estável. Nenhum
   CLOSE do grupo atual participa do preço de execução ou do sizing nesse grupo.
6. Só depois de todos os fills, marcar os CLOSEs e gerar os próximos sinais.
   Ativos ausentes mantêm a última marca conhecida, como no paper.

O último sinal sem próximo candle não executa. Gaps não são preenchidos com dados
futuros; a validade do sinal continua sendo a regra de 1h do risco M2/M3.
Não há liquidação artificial no último candle. Posições abertas permanecem
marcadas pelo último fechamento conhecido. Estes testes cobrem look-ahead básico;
o núcleo não promete eliminar vieses da seleção do histórico ou do universo.

## Métricas e invariantes

Dinheiro é `Decimal`; JSON usa strings decimais, contagens inteiras e `null`
para razões indefinidas. Valores monetários e percentuais têm 10 casas.

| Campo | Definição |
| --- | --- |
| `return_pct` | `(equity final - initial cash) / initial cash * 100` |
| `max_drawdown` | Maior `pico anterior - equity`, em USD |
| `max_drawdown_pct` | Maior `(pico anterior - equity) / pico anterior * 100` |
| `closed_trades` | Roundtrips BUY → SELL completos; não conta fills isolados |
| `win_rate_pct` | Operações com lucro líquido positivo / encerradas * 100 |
| `average_profit` | Média dos lucros líquidos positivos |
| `average_loss` | Média das perdas líquidas negativas, com sinal negativo |
| `profit_factor` | Soma dos lucros líquidos / módulo da soma das perdas líquidas |

Drawdown usa equity a cada fechamento de grupo e capital inicial como primeiro
pico; não mede mínima intrabar. Máximos monetário e percentual são calculados
independentemente. Lucro líquido por operação desconta fees de entrada e saída.
Slippage já está no preço do fill: seu campo mede impacto, não uma segunda dedução.
Sem encerramentos, win rate é `null`. Sem vencedoras/perdedoras, a média respectiva
é `null`. Profit factor sem perdas é `null` com `no_losses`; sem operações,
`no_closed_trades`; havendo somente perdas, é zero. Empates entram no denominador
de win rate e não nas médias de ganhos/perdas. Nunca emitir Infinity/NaN.

Reconciliação em cada grupo, herdada do paper:

```text
market_value = soma(quantity * mark)
equity = cash + market_value
unrealized_pnl_gross = soma((mark - average_price) * quantity)
total_pnl_net = equity - initial_cash
total_pnl_net = realized_pnl_gross + unrealized_pnl_gross - fees
total_pnl_net = soma(net_pnl de trades encerrados)
                + unrealized_pnl_gross - fees de entradas ainda abertas
```

A última identidade também é validada antes de devolver o relatório. Falha de
reconciliação aborta o run, sem publicação parcial. Compras têm quantidade inteira,
custo com fee de no máximo 10% do equity e cash suficiente. Sem margin, short ou
pyramiding; SELL fecha integralmente a LONG. HOLD, risco REJECTED e ações sem
posição aplicável não geram ordens; rejeição financeira não altera saldo.

## Executar no PowerShell

Na raiz, com dependências instaladas (`uv sync --locked`) e banco local configurado:

```powershell
docker compose up -d --wait postgres
uv run alembic upgrade head
uv run python -m scripts.backtest freeze --provider alpaca --symbols SPY AAPL TSLA --initial-cash 10000 --fee-bps 1 --slippage-bps 5 --output .artifacts/m4-dataset.json
uv run python -m scripts.backtest run .artifacts/m4-dataset.json --output .artifacts/m4-report.json
uv run python -m scripts.backtest run .artifacts/m4-dataset.json --output .artifacts/m4-report-repeated.json
Get-FileHash .artifacts/m4-report.json,.artifacts/m4-report-repeated.json -Algorithm SHA256
```

`freeze` lê somente histórico já persistido; não baixa dados Alpaca. Use
`--provider simulator --symbols SPY` para candles locais simulados já existentes.
Todos os símbolos pedidos devem existir. Os dois comandos `run` funcionam com o
banco/API desligados. Para mudar custos, gere outro manifest com os argumentos
correspondentes; editar conteúdo mantendo o hash antigo é recusado.
Não retomar/resetar a carteira paper para executar backtests.

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run mypy scripts/backtest.py
docker compose --profile test up -d --wait postgres postgres_test
$env:RUN_DB_TESTS = '1'
uv run pytest -q
```

Os testes PostgreSQL selecionam exclusivamente `trading_bot_test` em 5433 e
limpam suas próprias tabelas. Para `alembic check`, em outra sessão PowerShell:

```powershell
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_PORT = '5433'
$env:POSTGRES_DB = 'trading_bot_test'
$env:POSTGRES_USER = 'test_only'
$env:POSTGRES_PASSWORD = 'test_only'
uv run alembic check
```

## Evidências de 2026-09-04

- Ruff format/check OK (96 arquivos); mypy OK (55 arquivos + CLI).
- **204 testes passaram: 155 unitários + 49 PostgreSQL**, incluindo 26 casos M4.
- Alembic: `No new upgrade operations detected`, revisão `0008_m3_paper`.
- Testes M4: contas manuais, drawdown, custos, fees abertas/fechadas, casos sem
  trades/ganhos/perdas, ausência de look-ahead, cross-asset, falta de capital,
  dataset inválido, corrupção de manifest, versão incompatível, atomicidade de
  arquivo e determinismo sob reordenação/contexto Decimal diferente.
- PostgreSQL: equivalência de todos os campos financeiros de cada snapshot com
  PaperStore; congelamento READ ONLY/REPEATABLE READ; mudança posterior no banco
  não muda o manifest; dois processos offline novos geram os mesmos bytes.
- Histórico local: 600 candles, 200 por SPY/AAPL/TSLA, de 2026-07-30 15:00 UTC a
  2026-09-03 21:00 UTC. 200 grupos temporais. Relatório resumido versionado em
  [evidence/m4-metrics.json](evidence/m4-metrics.json).
- Capital inicial USD 10000, fee 1 bps, slippage 5 bps: equity final
  **10085.5935535635**, retorno **0.8559355356%**, drawdown **79.2770600893 USD /
  0.7875952672%**, **130 trades**, win rate **29.2307692308%**, lucro médio
  **10.0828772665**, perda média **-3.2624657118**, profit factor **1.2765396068**.
- 261 ordens/fills; 38 vencedoras, 92 perdedoras; 1 posição aberta. Fees
  **21.7211064365**, impacto de slippage **108.6053400000**, P&L líquido
  **85.5935535635**. Nenhum ajuste de estratégia para melhorar esse resultado.
- Arquivos completos locais `.artifacts/m4-report{,-repeated}.json`: SHA-256
  `7db1fd1125c4af2bd9e9820f844eed1d74425c43548f366464a8dab24d6d31c3`, idênticos.
  O hash `result_hash` interno exclui o próprio campo e difere do hash do arquivo.
- Todas as tabelas paper tiveram o mesmo hash antes/depois:
  `4683dd6e623225ec619e316dbd845d005ec5787dc9e6682447e2cd525dcec614`.
  Controle continuou pausado. Busca por TradingClient/submit_order/URLs de ordens
  em `services`, `packages` e `scripts`: nenhuma ocorrência.

## Bugs, incidentes e limites

O teste de entrada float reproduziu `AttributeError` no validador `Candle`, que
chamava `is_finite` sem verificar o tipo. Correção: rejeitar valores não Decimal
com `ValueError`. Sem alteração da matemática de entradas válidas.

O Docker falhou novamente ao iniciar `dockerInference`. As primeiras tentativas
de PostgreSQL tiveram erros de conexão. Recuperação reversível: Docker encerrado,
apenas WSL `docker-desktop` terminado, diretórios de sockets preservados como
`run.stale-20260904075820` e `docker-secrets-engine.stale-20260904075820`; Desktop
reiniciado. Sem reset de fábrica, exclusão de volume ou alteração de credenciais.
Depois, ambos os bancos Healthy e todos os testes passaram. A causa recorrente
do Docker Desktop não foi corrigida pelo projeto; preservar backups dos sockets.

Um comando auxiliar de evidência tentou ler a coluna inexistente `checkpoint`;
foi corrigido antes do congelamento, sem escrita no banco. Permanece um warning
de depreciação Starlette/AnyIO nos testes, sem falhas.

Relatórios completos e histórico congelado ficam locais em `.artifacts`, fora
do Git; transportar o mesmo manifest é necessário para reprodução em outra máquina.
Hashes detectam alteração acidental, não autenticam arquivos contra um atacante
local que possa modificar conteúdo e recalcular checksums. O relatório é dado JSON,
nunca código executável. Ausência de gráfico/replay visual e de diferenciação no
dashboard é deliberada neste recorte: aceite **do núcleo**, não de todo o M4 visual.
