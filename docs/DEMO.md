# Demonstração — M1.5 em validação

Resultados anteriores pertencem a [DEMO-M1](DEMO-M1.md). O estado atual e os comandos executados estão em [STATUS](STATUS.md); instalação e recuperação em [RUNBOOK](RUNBOOK.md).

## Demonstrado nesta correção

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

## Próxima demonstração de dados reais — ainda pendente

1. Confirmar as credenciais localmente e habilitar explicitamente RUN_ALPACA_SMOKE_TEST=1.
2. Executar o smoke limitado. Mercado regular fechado deve informar streaming not validated.
3. Iniciar um único backend com MARKET_DATA_PROVIDER=alpaca.
4. Conferir SPY/1h fechado no PostgreSQL, REST e replay WS.
5. Abrir app normal no Xiaomi; trocar SPY → AAPL → TSLA e conferir séries independentes.
6. Durante sessão apropriada, observar uma nova hora fechada nativa, com margem de fechamento e intervalo de atualização.
7. Reiniciar backend e recuperar conexão sem duplicar candle/evento/Signal/RiskDecision.

A tela deve identificar DADOS REAIS e fonte/feed; análise/decisão permanecem simuladas. Nenhuma ordem existe. Não concluir M1.5 por histórico sozinho, ACK do socket ou teste com fake.
