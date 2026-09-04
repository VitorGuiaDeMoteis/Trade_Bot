# Demonstração — M1.5 em validação

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
