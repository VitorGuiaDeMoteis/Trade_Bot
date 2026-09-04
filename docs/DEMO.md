# M4 — demonstração física concluída

[Fluxo executado, screenshots e comandos](M4_ACCEPTANCE.md). Summary, curva,
Trades, Replay e export JSON foram validados no Xiaomi em retrato/paisagem.
Carteira paper preservada e pausada. Registros abaixo descrevem recortes anteriores.

---

# Demo M4 — núcleo por CLI

1. Seguir [freeze/run](M4_CORE.md#executar-no-powershell) para congelar candles do
   PostgreSQL local. Não retomar a carteira paper.
2. Rodar duas vezes o mesmo manifest e comparar SHA-256 dos relatórios completos.
3. Ler `metrics`, `equity_curve`, `trades`, `outcomes` e `positions` no JSON;
   todos pertencem a BACKTEST. Dinheiro é string Decimal, não float.
4. Confirmar as contas e os testes de ausência de look-ahead/isolamento PostgreSQL
   descritos em [M4_CORE](M4_CORE.md#evidências-de-2026-09-04).

Demonstração executada: 600 candles, 130 roundtrips encerrados, 261 fills e uma
posição aberta; dois relatórios idênticos, carteira corrente ainda pausada e
inalterada. [Métricas exatas e hashes](evidence/m4-metrics.json).
Não há demonstração visual/tablet neste recorte autorizado.

---

# Demo M3 — pausa física validada

Xiaomi 23073RPBFG, 1791a20e, Android 15: abrir Carteira Simulada, observar RUNNING,
tocar PAUSAR SIMULAÇÃO e confirmar SIMULAÇÃO PAUSADA. Carteira permanece visível;
aba Positions mantém TSLA 3 ações. CLI replay falha com paper_paused sem nova ordem.

[Capturas, valores e roteiro executado](M3_STOP.md#testes-e-prova-física).
O estado atual está pausado. Retomada só por ação explícita do operador na CLI.

---

# Demonstração — M2 Decisions / Strategy + Risk

Recorte implementado, aguardando aceite do usuário. M3 não iniciado. Para executar: [RUNBOOK](RUNBOOK.md). Gates e limitações: [STATUS](STATUS.md).

## Roteiro M2

1. Iniciar PostgreSQL, aplicar `alembic upgrade head` (0007_m2_decisions) e iniciar um único backend. Neste ambiente, usar a configuração Alpaca já autorizada e o histórico persistido; não inserir credenciais no app.
2. Confirmar `/health` HTTP 200 e consultar `/api/v1/decisions?symbol=SPY&timeframe=1h&limit=50`.
3. Abrir o app normal no Xiaomi via USB/adb reverse. Na tela de mercado, tocar **Decisões**.
4. Selecionar SPY, AAPL e TSLA. Cada seleção apresenta sua janela de 50 decisões, sem misturar séries. Rolar os cartões e tocar em um deles.
5. Conferir OHLCV, UTC de abertura/fechamento, versão da estratégia, reason do sinal, reason/instante do risco e identificadores. Voltar preserva a posição da timeline.
6. Em HOLD, confirmar **SEM AÇÃO**. APPROVED é resultado histórico; não existe ordem. Atualizar consulta apenas repete GET.

## Evidências M2

| Ativo | Timeline | Rolagem | Detalhe |
| --- | --- | --- | --- |
| SPY | [Retrato](evidence/m2-xiaomi-spy-portrait.png) | [Mais decisões](evidence/m2-xiaomi-spy-timeline-scroll.png) | [SELL / OHLCV](evidence/m2-xiaomi-spy-detail.png) |
| AAPL | [Retrato](evidence/m2-xiaomi-aapl-portrait.png) | [Mais decisões](evidence/m2-xiaomi-aapl-timeline-scroll.png) | [BUY / OHLCV](evidence/m2-xiaomi-aapl-detail.png) |
| TSLA | [Retrato](evidence/m2-xiaomi-tsla-portrait.png) | [Mais decisões](evidence/m2-xiaomi-tsla-timeline-scroll.png) | [HOLD / OHLCV](evidence/m2-xiaomi-tsla-detail.png) |

Paisagem: [visão geral TSLA](evidence/m2-xiaomi-tsla-landscape.png) e [timeline rolada](evidence/m2-xiaomi-tsla-landscape-scroll.png).

Verificação estruturada: [API e correspondência com PostgreSQL](evidence/m2-decisions-api-validation.json), [interação física Xiaomi](evidence/m2-xiaomi-validation.json). As contagens abaixo se referem à janela observada nesta validação, não a rentabilidade:

| Ativo | BUY | SELL | HOLD | Decisões disponíveis na API/DB |
| --- | --- | --- | --- | --- |
| SPY | 24 | 24 | 2 | 200 |
| AAPL | 26 | 23 | 1 | 200 |
| TSLA | 23 | 20 | 7 | 200 |

As 600 avaliações reais persistidas são APPROVED. Rejeição por pausa/expiração foi testada com dados fictícios, sem adulterar histórico real para a demonstração. A UI informa que o feed exibido corresponde à configuração atual; o candle legado armazena provider, sem coluna de feed histórico.

## Histórico M1.5 (preservado)

Resultados anteriores pertencem a [DEMO-M1](DEMO-M1.md). O estado atual e os comandos executados estão em [STATUS](STATUS.md); instalação e recuperação em [RUNBOOK](RUNBOOK.md).

## Histórico Alpaca real no Xiaomi — aprovado em 2026-09-03, 21:14 BRT

Xiaomi 1791a20e conectado por USB, backend Alpaca/IEX existente reutilizado e estado market_closed tratado normalmente. Foram conferidos 200 candles por ativo na API/PostgreSQL, replay interno e navegação física SPY → AAPL → TSLA → SPY. O último OHLCV exibido coincide com o registro da série selecionada.

Capturas em retrato, revisadas sem overflow visível:

- [SPY](evidence/m15-real-xiaomi-spy-portrait.png).
- [AAPL](evidence/m15-real-xiaomi-aapl-portrait.png).
- [TSLA](evidence/m15-real-xiaomi-tsla-portrait.png).
- [Retorno para SPY](evidence/m15-real-xiaomi-spy-return-portrait.png).

O app normal ficou aberto em SPY. Streaming externo durante sessão regular e uma nova hora fechada ao vivo permanecem pendentes. Esta validação não inicia M2/M3.

## Histórico da rodada anterior — demonstração simulada

1. Backend corrigido em modo simulator, PostgreSQL na revisão 0006_m15_integrity e /health 200.
2. APK normal instalado e aberto no Xiaomi 23073RPBFG, serial 1791a20e, Android 15.
3. Histórico TEST/1h, selo SIMULADO, simulação acelerada e atualização por WebSocket.
4. Retrato 1200×1920 e paisagem 1920×1200 com layout rolável, textos legíveis e sem overflow visível.
5. Botões de inspeção com área mínima 48 dp verificada em testes.
6. Rotação restaurada: free, user_rotation=0, accelerometer_rotation=1.

Os [testes físicos](evidence/m15-tablet-tests.txt) passaram nas duas orientações, recebendo histórico REST e novo evento WS e acionando a inspeção por toque. Após a integração, o APK normal foi reinstalado com sucesso; a recusa inicial do instalador foi resolvida na nova tentativa.

Capturas revisadas:

- [Retrato no display inteiro](evidence/m15-tablet-simulator-portrait.png).
- [Paisagem no display inteiro](evidence/m15-tablet-simulator-landscape.png).

São **dados simulados no código corrigido**, não prova de Alpaca real.

## Roteiro de dados reais — etapas de histórico concluídas; streaming pendente

1. Confirmar as credenciais localmente e habilitar explicitamente RUN_ALPACA_SMOKE_TEST=1.
2. Executar o smoke limitado. Mercado regular fechado deve informar streaming not validated.
3. Iniciar um único backend com MARKET_DATA_PROVIDER=alpaca.
4. Conferir SPY/1h fechado no PostgreSQL, REST e replay WS.
5. Abrir app normal no Xiaomi; trocar SPY → AAPL → TSLA e conferir séries independentes.
6. Durante sessão apropriada, observar uma nova hora fechada nativa, com margem de fechamento e intervalo de atualização.
7. Reiniciar backend e recuperar conexão sem duplicar candle/evento/Signal/RiskDecision.

A tela deve identificar DADOS REAIS e fonte/feed; análise/decisão permanecem simuladas. Nenhuma ordem existe. Não concluir M1.5 por histórico sozinho, ACK do socket ou teste com fake.
