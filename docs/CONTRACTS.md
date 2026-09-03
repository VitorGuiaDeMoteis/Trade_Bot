# Contratos M1.5 — versão 2.0

Somente leitura local. A versão 2.0 rompe com o cursor Alpaca por timestamp e com snapshots que misturavam ativos. Contratos M1 antigos estão em [CONTRACTS-M1](CONTRACTS-M1.md); não usar seus exemplos como contrato atual.

## Candle fechado

| Campo | Significado |
| --- | --- |
| candle_id | UUID estável da identidade de mercado |
| provider / symbol / timeframe | simulator/TEST/1h ou alpaca/ativo configurado/1h |
| open_time / close_time | UTC; close_time = open_time + 1 hora |
| is_closed | Sempre true nas leituras e eventos persistidos |
| open / high / low / close | Strings Decimal, armazenamento NUMERIC(28,10); não converter para float na ingestão |
| volume | Inteiro não negativo |
| regime | Regime fictício no simulador; null para Alpaca |
| stream_id | Série independente; para Alpaca, UUID de provider+symbol+timeframe |
| sequence | Cursor de ingestão consecutivo a partir de 1 dentro da série |

Identidade única global: provider+symbol+timeframe+open_time. Cursor não é timestamp nem índice global entre ativos. Um backfill atrasado pode ter horário anterior e cursor maior; o gráfico ordena por horário, o transporte avança pelo cursor.

Somente 1h está validado. A REST Alpaca recebe explicitamente 1Hour e um símbolo por chamada. Minutos do WebSocket nunca viram candles 1h. A REST exclui barras cuja hora ainda não fechou, com margem adicional de 60 segundos; a persistência e a estratégia também rejeitam parciais.

## GET /api/v1/market/candles

Parâmetros: symbol (padrão: primeiro configurado), timeframe=1h, limit=200 (1..500), after>=0, through>=0, stream_id opcional.

- Sem after: últimos limit registros por sequência da série, entregues em sequência crescente.
- Com after: sequence > after, limitado por through quando informado.
- high_watermark fixa o maior cursor considerado. Paginar com o mesmo through.
- cursor é a última sequência retornada, ou after sem novidades; série vazia começa em zero.
- has_more equivale a cursor < high_watermark.
- Resposta: schema_version=2.0, stream_id, symbol, timeframe, candles, cursor, high_watermark, has_more, last_updated_at, market_data, correlation_id.
- last_updated_at é o UTC da persistência, não o horário virtual/do mercado.

Exemplo: /api/v1/market/candles?symbol=SPY&timeframe=1h&limit=200.
Para percorrer tudo: after=0 e paginação até has_more=false.
422: série/parâmetros inválidos; 409: stream_changed ou cursor_reset_required; 503: database_unavailable. Falha não se converte em histórico vazio.

## WS /api/v1/market/events

Conectar com symbol, timeframe=1h, stream_id da resposta REST e after=cursor. Quando symbol é omitido, o stream_id resolve uma série configurada. Nunca misturar um cursor SPY com AAPL.

Eventos persistidos: type=event, schema_version=2.0, event_type=market.candle.closed, event_id, stream_id, sequence, occurred_at, correlation_id e payload Candle. Publicação somente após commit; replay preserva o event_id.

Heartbeat a cada 2 segundos: type=stream.status, schema_version=2.0, stream_id, cursor, correlation_id, database e market_data. É informação de transporte, não um novo evento de domínio.

1008: série/cursor/origem inválidos; 1013: banco indisponível. O socket não aceita comandos de operação. Cliente recupera lacunas via REST antes de retomar o WS.

## market_data e /health

market_data contém state, provider, feed, symbols, timeframe, session, last_message_at, last_bar_at, last_persisted_at, error, accelerated e interval_seconds.

- connecting: conexão/handshake pendentes; connected: handshake/subscrição confirmados.
- reconnecting: transporte temporariamente indisponível, backoff em andamento.
- configuration_error: credenciais/permissões/assinatura/configuração rejeitadas.
- market_closed: **sessão regular** fechada pelo calendário XNYS local, incluindo feriados, DST e encerramento antecipado.
- delayed: sessão regular aberta há mais de duas horas sem barra recente suficiente.
- degraded: ingestão inválida, conflito de conteúdo ou banco indisponível.
- offline/stopped/starting/stalled: ciclo local; stalled só se aplica ao produtor acelerado do simulador.

Market Data pode incluir pré/after-market. market_closed não afirma ausência desses negócios. Candles nativos 1Hour não são forçados para janelas de 9:30 da sessão regular.

Saúde mantém envelope 1.1: HTTP 200 apenas com banco/revisão prontos e estado connected ou market_closed; demais estados resultam em 503. Banco indisponível prevalece no Flutter sobre um provider conectado. Heartbeat saudável do backend não prova mercado aberto.

## Atomicidade, duplicatas e reinício

Candle, system_event, Signal e RiskDecision são gravados na mesma transação. UNIQUE por candle+strategy_version e RiskDecision por Signal. Mesmo candle/conteúdo retorna o evento anterior e registra market.candle.duplicate; não roda estratégia nem risco outra vez.

Mesmo identificador de mercado com conteúdo diferente falha, registra market.ingestion.failed e interrompe a ingestão em degraded. Não há sobrescrita ou revisão automática de decisões. Falha transitória do banco repete o mesmo item antes de pedir o próximo.

Sequência é alocada sob advisory lock por série, no mesmo commit; rollback não deixa buraco. O simulador retoma sequence e último fechamento persistidos. Como a identidade de mercado é global, mudar apenas seed no mesmo início virtual pode conflitar; usar outro início UTC para outro conjunto simulado.

Flutter mantém até 2.000 candles na memória e desenha os últimos 60 em ordem de mercado. Trocar ativo cancela a conexão anterior, limpa seu cursor e faz nova consulta REST. Respostas antigas são descartadas por geração da conexão.

## Dados anteriores à correção

A migração 0006_m15_integrity preserva em legacy_market_archive os registros Alpaca anteriores, incluindo os eventos, sinais e decisões relacionados. Não é possível provar quais vinham de minute bars. Esses registros não entram em REST/WS nem são tratados como horas validadas. Histórico deve ser reimportado da fonte canônica após autorização do teste real.
