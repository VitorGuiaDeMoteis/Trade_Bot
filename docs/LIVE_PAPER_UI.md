# Live Paper UI

Dashboard Flutter para observação de **Alpaca Paper** (dinheiro fictício) + multi-timeframe.

Status: **UI mock / design preview** nesta branch. Backend Live Paper ainda não validado.

## Layout

Experiência principal: **tablet landscape**.

Hierarquia visual:

1. Mode / dinheiro fictício (`ALPACA PAPER • DINHEIRO FICTÍCIO`)
2. Saúde (broker, market, stale)
3. Equity / Day P&L
4. Chart (SPY + selector 5m/15m/1h)
5. Posições
6. Última decisão (SIGNAL → RISK → RESULTADO)
7. Risk
8. Ordens recentes
9. AI Observer (resumo pequeno)

### Responsive

| Viewport | Navegação | Layout |
|----------|-----------|--------|
| Tablet landscape (≥900px) | `NavigationRail` | Painéis em colunas |
| Tablet portrait / phone | `NavigationBar` | Coluna vertical, mesmos dados |

Destinos: Resumo · Mercado · Decisões · Ordens · Backtest · Sistema

## Contrato esperado

`GET /api/v1/live-paper/dashboard` — schema `1.0` (ver `lib/src/live_paper/models.dart`)

Também:

- `GET /api/v1/live-paper/orders`
- `GET /api/v1/live-paper/fills`
- `GET /api/v1/market/candles?symbol=SPY&timeframe=5m|15m|1h&limit=200`

Campos monetários são **strings Decimal**. O Flutter só formata para exibição; **não recalcula** P&L oficial.

Chart markers (`BUY`/`SELL`) são opcionais. Lista vazia da API = sem markers (não inventar).

## Timeframes

- Default visual: **15m**
- Timeframe operacional da strategy: vem do dashboard (`operational_timeframe`, esperado `15m`) e recebe indicação `15m · STRATEGY`
- Tocar 5m/1h muda **somente visualização**

## Mock status

Sem `API_BASE_URL` (ou `USE_LIVE_PAPER_MOCK=true`), o app usa `MockLivePaperApi`.

Qualquer screenshot gerado nesta branch é **MOCK / DESIGN PREVIEW** — não é validação Xiaomi/API real.

Screenshots: `docs/evidence/live-paper-ui-*-mock.png` (goldens also under `apps/mobile_app/test/goldens/` for `flutter test --update-goldens`)

## Estados de UI cobertos

loading · offline · API error · no positions · no orders · market closed/degraded · broker offline · risk paused/degraded · stale market · observer OK/DEGRADED

## Pendências backend

- Implementar endpoints Live Paper reais (contrato acima)
- Snapshot REST + (futuro) WebSocket incremental
- Markers reais ligados a fills/decisões
- Não apresentar mock como validação live

## Fora de escopo nesta branch

- Backend Alpaca
- Trading manual (sem botões BUY/SELL)
- Alterações em Strategy / Risk / PaperExecutor
- M6 / fechamento M5
