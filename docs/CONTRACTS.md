# Contratos M1

Somente leitura local. REST também em http://127.0.0.1:8000/docs com o backend executando. Exemplos reais: [snapshot](evidence/m1-contract-snapshot.json) e [evento persistido](evidence/m1-contract-event.json).

## Candle 1.0

| Campo | Tipo e significado |
| --- | --- |
| candle_id | UUID determinístico, único |
| stream_id | UUID de algoritmo/seed/início/símbolo/timeframe |
| sequence | Inteiro crescente a partir de 1; cursor dentro do stream |
| symbol / timeframe | TEST / 1h |
| open_time / close_time | ISO 8601 UTC; intervalo virtual de uma hora |
| open / high / low / close | Strings decimais, quatro casas; banco NUMERIC(24,4) |
| volume | Inteiro não negativo, fictício |
| regime | uptrend, downtrend, sideways ou volatile |

Candles são imutáveis pela API. Preços positivos; high >= open/close e low <= open/close, implicando high >= low. Mesmo stream nunca repete sequência nem abertura. UUID sozinho não ordena eventos.

## GET /api/v1/market/candles

Parâmetros: limit=200 (1..500), after opcional (>=0), through opcional (>=0), stream_id UUID opcional.

- Sem after: últimos limit candles, ordenados crescentemente.
- Com after: sequence > after, até through quando fornecido.
- high_watermark fixa o maior índice considerado. Nas páginas seguintes enviar through igual a esse valor.
- cursor: última sequência retornada ou after quando não há novidades. Snapshot vazio inicial usa zero.
- has_more indica páginas restantes até high_watermark.
- last_updated_at: horário real UTC da persistência do último candle do snapshot, distinto do relógio virtual.
- simulator: state, seed, start, interval_seconds, accelerated, last_persisted_at e error.
- Resposta inclui schema_version="1.0", stream_id, symbol, timeframe, candles e correlation_id.

X-Correlation-ID UUID é preservado no cabeçalho/corpo e log HTTP. Valor ausente/inválido é substituído.

Erros: 422 parâmetros inválidos; 409 stream_changed ou cursor_reset_required (refazer snapshot sem cursor); 503 database_unavailable. Banco indisponível não vira histórico vazio.

Exemplos PowerShell:

    $page = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/market/candles?limit=200'
    Invoke-RestMethod "http://127.0.0.1:8000/api/v1/market/candles?after=$($page.cursor)&through=$($page.high_watermark)&stream_id=$($page.stream_id)&limit=200"

Para percorrer desde o primeiro candle, começar com after=0. A próxima página só é necessária quando has_more=true. Sem through, nova consulta considera o limite superior mais recente.

## WS /api/v1/market/events

Conectar com stream_id do snapshot e after=cursor. Entrega replay persistido posterior ao cursor, seguido das novas transações. Ordem crescente, lotes internos de até 100, polling 200 ms. Nenhum evento é publicado de transação aberta.

Envelope do evento:
- type: event
- schema_version: 1.0
- event_id: UUID estável em replay
- event_type: market.candle.closed
- occurred_at: persistência em tempo real UTC
- correlation_id: UUID preservado no banco, log do produtor e replay
- stream_id, sequence
- payload: Candle 1.0

Heartbeat de transporte a cada dois segundos: type=stream.status, schema_version=1.0, stream_id, cursor, correlation_id, database e simulator. É efêmero; não é candle nem evento de decisão.

Stream/cursor inválido: fechamento 1008 ou rejeição da abertura. Banco indisponível: 1013. Origem browser externa é rejeitada; cliente nativo USB não envia Origin. Nenhum comando aceito no socket.

## Recuperação Flutter

1. Validar snapshot, sequência, identidade, timestamps e OHLCV.
2. Preencher páginas até high_watermark, guardando no máximo 500 candles na memória.
3. Conectar WS depois do cursor aplicado. Commit entre REST e WS entra pelo replay.
4. Ignorar eventos com sequence <= cursor; validar ID/tempo e continuidade dos novos.
5. Lacuna/dados inconsistentes conservam último gráfico válido e iniciam recuperação.
6. Backoff 1/2/4/8/15 segundos, teto 15; socket silencioso expira em 8 segundos.
7. Antes de reabrir WS, consultar REST after=cursor com stream_id. Troca/reset 409 inicia snapshot novo.

Entrega ao menos uma vez, efeito visual deduplicado. Sem armazenamento offline persistente no aparelho; reabrir busca os últimos 200 candles.

## GET /health 1.1

Preserva campos M0 e adiciona simulator. HTTP 200 quando database=up e simulator.state=running. HTTP 503 para starting/stopped/degraded/stalled ou banco/schema não pronto. Stalled após falta de progresso por max(10, 2 × intervalo + 5) segundos.

## Persistência e relógio

Migração 0002_m1 após 0001_m0: candles + system_events, FK, UNIQUE e checks. Inseridos na mesma transação. Evento referencia candle imutável; payload reconstruído na leitura.

Seed padrão 42, início virtual 2026-01-01T00:00:00Z e intervalo 2 s. Intervalo 0,1..3600 s; abaixo de 3600 é acelerado. Ritmo não muda valores/stream_id. Seed/início diferentes selecionam outro stream. Reinício retoma último fechamento; não preenche tempo real perdido.

Um único worker/produtor. Advisory lock serializa avanços e UNIQUE garante idempotência, mas múltiplos produtores mudariam o ritmo. Polling/retensão integral bastam ao M1 local; cliente desenha últimos 60 candles. Não há limpeza automática.

