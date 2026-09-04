# M4 — núcleo implementado e validado (2026-09-04)

Branch `codex/m4-backtesting`, base `fc4aee8d20198a8656c5f375ce9e0b16da423614`.
Backtest offline compartilhando Strategy/Risk/PaperExecutor, dataset congelado,
replay determinístico e exportação JSON com todas as métricas do núcleo M4.
Sem Flutter, gráficos, Trading API, IA ou M5; sem merge. Aceite do núcleo entregue
para revisão; replay visual/dashboard permanecem fora do recorte autorizado.

**Gates finais:** `uv run ruff format --check .` (96 arquivos), `uv run ruff check .`,
`uv run mypy` (55 arquivos), `uv run mypy scripts/backtest.py`: OK.
`docker compose --profile test up -d --wait postgres postgres_test`: ambos Healthy.
`$env:RUN_DB_TESTS='1'; uv run pytest -q`: **204 passed**, 155 unitários + 49 PostgreSQL.
26 casos M4 novos. `uv run alembic check` no banco dedicado 5433: nenhuma alteração.
Warning de depreciação Starlette/AnyIO permanece, sem falhas.

Duas execuções CLI do mesmo manifest de 600 candles SPY/AAPL/TSLA produziram bytes
idênticos. Retorno 0.8559355356%, drawdown 0.7875952672%, 130 trades, win rate
29.2307692308%, lucro médio 10.0828772665 USD, perda média -3.2624657118 USD,
profit factor 1.2765396068. Capital 10000 USD, fee 1 bps, slippage 5 bps.
Tabelas da carteira paper idênticas antes/depois; controle permaneceu pausado.

Bug corrigido: Candle com float falhava com AttributeError; agora rejeita
explicitamente não Decimal com ValueError, coberto por regressão.
Docker voltou a falhar em dockerInference, causando erros de conexão nas primeiras
integrações. Sockets preservados com sufixo `.stale-20260904075820`, WSL exclusivo
Docker terminado e Desktop reiniciado: recuperação sem reset/exclusão de volumes.
Validações foram repetidas com sucesso. Recorrência do problema Docker continua
sendo limitação ambiental. Nenhuma mudança global de SDK/Android; Xiaomi não foi
revalidado porque este recorte exclui Flutter.

[Comandos completos, invariantes, testes, resultados e limites](M4_CORE.md).
[Métricas e hashes versionados](evidence/m4-metrics.json). Logs completos locais:
`.artifacts/m4-all-tests.txt`, `.artifacts/m4-unit-final.txt`; manifest e dois
relatórios em `.artifacts/m4-*.json`. Próximo passo depende da revisão do usuário;
M5 não iniciado. Registros abaixo são históricos.

---

# M3 — blocker de pausa resolvido em 2026-09-04

**M3 acceptance: APPROVED.** Base `ffd94fb33c408d7ea1f192c2e189b999f9a4b654`.
Flutter e backend agora compartilham STOP local sem segredo no APK. Peer/Host local,
marcador não secreto, body vazio, rejeição de Origin/browser/proxy; resume/reset CLI.
Botão PAUSAR SIMULAÇÃO; depois SIMULAÇÃO PAUSADA e instrução de CLI, sem retomada remota.

Gates: Ruff format/check + mypy OK; pytest **178 passaram (132 unitários + 46 PostgreSQL)**;
Flutter analyze limpo; Flutter test **71 passaram**; APK debug compilado e instalado.
Busca sem Trading API externa ou controle antigo no código Flutter.

Xiaomi 23073RPBFG / 1791a20e / Android 15 API35: RUNNING → toque em PAUSAR SIMULAÇÃO
→ PAUSED. Cash USD 9084.3458912448, LONG TSLA 3 ações e 1 ordem/fill preservados.
Tentativa CLI de replay bloqueada por paper_paused; STOP repetido idempotente;
nenhuma alteração das tabelas paper nessas tentativas. App sem crash/overflow observado.
Backend e tablet deixados disponíveis; simulação **pausada** no checkpoint 2/200,
dataset congelado de 600 candles. Backup dev local antes da demonstração.

[Contrato, threat model, comandos, resultados e capturas](M3_STOP.md).
Avisos de terceiros Starlette/AnyIO e SDK XML não impediram testes/build.
Não houve merge, avanço M4 ou alteração global de Android/SDK. Registros abaixo são históricos.

---

# Auditoria final M3 — 2026-09-04

**M3 financial/integrity audit: APPROVED** — escopo financeiro, persistência e segurança.

Pull explícito de `origin/codex/m3-paper` confirmou a base
`21a467526cf9bc67114bb392a32caef7b3e9f953`. Foram corrigidas falhas reproduzidas de
hash/dataset, retomada concluída, checkpoint, vínculo de ordem, marcas, snapshots
históricos, controle ativo, precisão e sobreposição temporal cross-asset. Consulta
Decisions passou a restringir resultados ao run ativo e falhar com 503 na corrupção.

Gates: Ruff format/check OK (86 arquivos); mypy OK (50 arquivos);
`RUN_DB_TESTS=1 uv run pytest -q`: **162 passed** (116 unitários + 46 PostgreSQL),
com um aviso de depreciação Starlette/AnyIO. **16 casos novos**.
Docker postgres_test Healthy; Alembic check sem alterações em
`0008_m3_paper`; busca por Trading API externa sem ocorrências em código.

A pausa concorrente, rollback após escritas financeiras e isolamento de leitores
foram verificados em PostgreSQL dedicado localhost:5433. Consulta somente leitura
em trading_bot_dev:5432 encontrou zero runs paper; nenhuma carteira histórica local
foi inventada ou criada nesta auditoria. Flutter visual e tablet não foram alterados
ou revalidados. Não houve merge nem avanço para M4.

[Relatório, invariantes, bugs, comandos e limitações](M3_FINANCIAL_AUDIT.md).
Os registros abaixo descrevem etapas anteriores e não ampliam este aceite focado.

---

# Status Atual: M3 - Carteira e Execução Simulada Concluída

Testes de backend (pytest + idempotência), lint (mypy, ruff), banco de dados (alembic) e frontend Flutter (analyze, test) finalizados com sucesso na branch `codex/m3-paper`.

## M2 — Decisions: recorte implementado e validado, aguardando aceite

Base exata: f6f8b748a264ddbaae17a7d1796eb8cdb2989862; branch codex/m2-decisions criada com working tree limpo. M1.5 permanece parcialmente validado conforme registro abaixo. M3 não iniciado; nenhuma execução.

Auditoria: baseline v1-deterministic e RiskEngine já existiam; motivos de risco persistidos. Acrescentados reason no domínio/sinais, migração 0007_m2_decisions, GET /api/v1/decisions e tela Flutter acessível pelo botão Decisões no mercado. Janela de 50 registros, seleção por ativo, resumo BUY/SELL/HOLD e detalhe OHLCV/UTC/justificativas/IDs.

Desenvolvimento e validação deste recorte concluídos; aceite formal do usuário pendente. O marco M2 não está marcado como aprovado. M3 não iniciado.

Backup local pré-migração: .artifacts/m2-before-decisions.sql (ignorado pelo Git). Backend anterior PID 89144 encerrado após conferir comando/caminho. Migração dev aplicada até 0007; alembic check sem diferenças. Fingerprints antes/depois confirmaram preservação integral das 2.193 linhas de cada tabela ativa (candles/events/signals/risk), exceto o novo reason, e das 2.956 entradas de quarentena. Isso inclui histórico simulado e os 600 candles Alpaca. Nenhum reason precisou do fallback legado neste banco.

### Comandos e resultados — 2026-09-03 BRT

Gates completos repetidos pelo script `./scripts/check.ps1 -Database` após corrigir os problemas encontrados; saída final zero. Registro local integral em .artifacts/m2-quality-gates.txt. Não publicar logs brutos do Flutter/Android, pois podem conter mensagens de outros aplicativos.

| Comando / verificação | Resultado |
| --- | --- |
| uv sync --locked | Lock preservado, dependências instaladas |
| uv run ruff format .; uv run ruff format --check . | Formatação aplicada; 72 arquivos conformes no gate final |
| uv run ruff check . | Sem erros |
| uv run mypy | Sem erros em 41 arquivos de código |
| uv run pytest -m 'not integration' | 104 passed; testes comuns bloqueiam HTTP/WS externos |
| docker compose config --quiet | Configuração válida |
| docker compose --profile test up -d --wait postgres postgres_test | Ambos saudáveis; dev 5432 e teste descartável 5433 |
| $env:RUN_DB_TESTS='1'; uv run pytest -m integration | 21 passed; migrações, rollback, unicidade, API por série, backfill, ordenação e idempotência |
| uv run alembic upgrade head; uv run alembic check | Dev em 0007_m2_decisions; nenhuma diferença de schema |
| flutter pub get --enforce-lockfile | Lock preservado |
| dart format lib test integration_test test_driver | Aplicado; check final sem alterações |
| flutter analyze --fatal-infos --fatal-warnings | Sem issues |
| flutter test | 60 passed; 18 testes novos M2, incluindo cinco viewports em 1x/2x, estados, seleção, detalhes, atraso de respostas, contraste e alvos de toque |
| adb devices -l; flutter devices | Xiaomi 23073RPBFG / 1791a20e, Android 15 API 35 arm64 |
| adb -s 1791a20e reverse tcp:8000 tcp:8000 | API local acessível ao aparelho |
| flutter run -d 1791a20e --no-resident --dart-define=API_BASE_URL=http://127.0.0.1:8000 | assembleDebug/build APK e instalação normais; app iniciado, PID 3503 |
| GET /health | HTTP 200, database=up, provider=alpaca, feed=iex, sessão regular fechada |
| GET /api/v1/decisions?symbol=SPY/AAPL/TSLA&limit=200 | 200 por ativo; igualdade integral candle + Signal + RiskDecision com PostgreSQL (600 itens) |
| GET Decisions com limit padrão 50 | Exatamente os primeiros 50 da consulta maior, ordenados por horário do candle |
| OpenAPI e POST /api/v1/decisions | Apenas GET nas três rotas HTTP de negócio/saúde; POST recusado com 405; nenhuma rota de execução |
| Checagem de resposta contra segredos locais | Nenhuma chave Alpaca presente no JSON; .env não alterado |

As primeiras execuções Flutter apontaram um lint de chaves e falhas nos testes de navegação (temporizadores de fakes não encerrados, alvo fora da área visível antes de concluir o layout e seletor ainda não construído na lista). Corrigidos lint, limpeza dos controllers e rolagem/sincronização dos testes; suíte final inteira verde. Nenhum teste foi removido ou ignorado. Aviso não bloqueante remanescente: DeprecationWarning de Starlette/AnyIO; Flutter informa versões mais recentes incompatíveis com o lock atual, sem falhas.

### Xiaomi e critérios de aceite demonstrados

App normal com histórico real Alpaca/IEX, sem teste de integração simulador instalado por cima. Seleção SPY → AAPL → TSLA, dez horários distintos percorridos por ativo, abertura dos detalhes e comparação OHLCV com API. Exemplos reais mais recentes: SPY SELL, AAPL BUY, TSLA HOLD. Foram revisadas as capturas de timeline e detalhe: texto legível e sem overflow visível. Chips medidos em 84 px = 48 dp; botão de atualizar com 56 dp. Testes de acessibilidade também passaram.

Retrato 1200x1920 e paisagem 1920x1200 testados no dispositivo. Orientação alterada temporariamente por `adb shell wm user-rotation lock 0/1` porque o aparelho estava fisicamente em paisagem; restaurados modo free e user_rotation=0 em finally. Nenhuma alteração permanente de SDK, Flutter, Android ou escala de texto. Texto 2x e celular foram validados por widgets, não por mudança global no tablet.

`adb shell pidof dev.tradingbot.mobile_app` permaneceu 3503 durante a navegação. `logcat -d --pid=3503 -v brief` filtrado: nenhum FATAL EXCEPTION, E/flutter, RenderFlex overflow ou Unhandled Exception. App permaneceu executando; API única em 127.0.0.1:8000 (worker observado 96124), sem expor a rede local.

| Critério | Evidência |
| --- | --- |
| BUY/SELL/HOLD determinísticos e explicáveis | Testes dos três candles, versão v1-deterministic e reason persistido; exemplos reais no Xiaomi |
| No máximo um Signal por candle/versão e um RiskDecision por Signal | Constraints, rollback e duplicatas concorrentes testados; grafo preservado na migração |
| Cada Signal do fluxo recebe RiskDecision | Gravação atômica no produtor configurado; correspondência completa dos 600 itens Alpaca |
| Expiração e pausa bloqueiam no RiskEngine | Testes até 1h inclusive, mais de 1h rejeitado e pausa com precedência; não existe comando de pausa/execução neste recorte |
| Timeline e detalhes auditáveis | Janela 50, contagens, ordem UTC, motivos históricos, IDs e fonte; HOLD explicitamente SEM AÇÃO |
| Nenhuma execução | Contrato execution=NONE, testes de rotas GET e UI NENHUMA ORDEM ENVIADA |

Evidências: [API/DB](evidence/m2-decisions-api-validation.json), [Xiaomi](evidence/m2-xiaomi-validation.json) e 14 screenshots `evidence/m2-xiaomi-*.png`; roteiro e links em [DEMO](DEMO.md). Código backend em 9a3a85c e Flutter/testes em 8e3fef3, ambos derivados da base pedida.

### Limitações e pendências preservadas

- Aceite formal deste recorte M2 pelo usuário; não avançar M3 nem fazer merge em main.
- M1.5: streaming Alpaca durante sessão regular e recebimento automático de uma nova hora fechada ao vivo continuam pendentes.
- As 600 avaliações reais existentes são APPROVED; REJECTED/pausa/expiração demonstrados com fakes e testes, sem fabricar histórico real.
- Janela de 50 na UI (até 200 na API), atualização manual, sem paginação. São limites definidos para este recorte.
- Feed histórico não armazenado no candle legado; detalhe identifica que IEX é a configuração atual.
- APK debug e validação física Android; builds de distribuição/iOS e execução de ordens fora deste escopo.

## M1.5 — validação parcial: histórico Alpaca real no Xiaomi aprovado

Histórico real SPY/AAPL/TSLA validado no PostgreSQL, REST, replay WebSocket interno e Flutter no Xiaomi. Ainda faltam streaming Alpaca durante sessão regular e uma nova hora fechada recebida ao vivo. O escopo permanece dados reais + análise/decisão simulada; nenhuma ordem ou Trading API.

### Validação Real (Mercado Fechado)

* Alpaca REST real ✅
* Histórico real SPY/AAPL/TSLA ✅
* PostgreSQL real ✅
* REST Trade_Bot ✅
* WS interno/replay ✅
* Idempotência ✅ — restart registrado na etapa anterior; consultas/replay e unicidade conferidos nesta rodada
* Flutter Xiaomi com histórico Alpaca real ✅
* Alpaca streaming ao vivo ⏳ pendente de sessão regular
* nova hora fechada recebida ao vivo ⏳ pendente

### Evidência atual — 2026-09-03, a partir de 21:11 BRT

Base desta rodada: f49bbe25e76feb67a4f464eead577579afa16fad na branch codex/m15-data-integrity. Checkout inicialmente limpo e sincronizado com origin; pull desnecessário. O registro anterior do Gemini em d814578 documenta a obtenção do histórico Alpaca real e o teste de restart. Esta rodada validou a chegada desse histórico ao aplicativo físico; não repetiu o teste de restart nem a importação externa.

| Etapa executada | Resultado observado |
| --- | --- |
| adb kill-server; adb start-server; adb devices -l; flutter devices | Xiaomi 23073RPBFG, 1791a20e, Android 15/API 35, arm64 disponível como device |
| adb -s 1791a20e reverse tcp:8000 tcp:8000; reverse --list | UsbFfs tcp:8000 tcp:8000 confirmado |
| docker compose up -d --wait | PostgreSQL saudável |
| MARKET_DATA_PROVIDER=alpaca na sessão; uv run alembic upgrade head; current | 0006_m15_integrity (head) |
| Backend existente em 127.0.0.1:8000, PID 89144 | Processo Alpaca válido reutilizado; nenhum backend paralelo iniciado |
| GET /health | HTTP 200, status=ok, database=up, mode=DADOS REAIS / EXECUÇÃO SIMULADA, provider=alpaca, feed=iex, state=market_closed |
| GET /api/v1/market/candles?symbol=SPY&timeframe=1h | 200 candles fechados SPY, apenas provider alpaca; cursor 200 |
| Mesma consulta para AAPL e TSLA | 200 candles fechados por ativo; três stream_id distintos, nenhuma mistura |
| Comparação REST/PostgreSQL | Todos os campos dos 600 candles retornados coincidem com as linhas ativas; UTC, OHLCV e fechamento conferidos |
| Quarentena | Nenhum candle retornado pertence a legacy_market_archive |
| WS interno /events por ativo, after=199 | Replay do candle 200 coincide integralmente com o último item REST nas três séries |
| SQL após navegação | Por ativo: 200 candles, 200 identidades distintas, 200 eventos, 200 Signal, 200 RiskDecision; consultas/replay não duplicaram registros |
| flutter run -d 1791a20e --no-resident --dart-define=API_BASE_URL=http://127.0.0.1:8000 em apps/mobile_app | APK normal compilado, instalado e aberto |
| Toques físicos via ADB: SPY → AAPL → TSLA → SPY | Seletor, título, contagem e gráfico mudaram para a série correta; último OHLCV exibido coincide com REST |
| Tela | DADOS REAIS, FONTE: ALPACA / IEX e Sessão regular fechada visíveis; rodapé informa análise/decisão simuladas e nenhuma ordem |
| Capturas em retrato | Quatro imagens 1200×1920 revisadas; gráfico e textos legíveis, sem overflow visível |
| Processo/log da aplicação | PID 25141 permaneceu ativo e em primeiro plano; sem FATAL EXCEPTION, erro Flutter ou RenderFlex overflow encontrado |
| Restauração da rotação | free, user_rotation=0, accelerometer_rotation=1; sem mudança permanente de configuração |

Valores do último candle exibido e conferido, para identificar concretamente cada série:

| Ativo | Fechamento UTC | Open | High | Low | Close | Volume |
| --- | --- | --- | --- | --- | --- | --- |
| SPY | 2026-09-03 21:00 | 773.115 | 773.115 | 772.39 | 772.39 | 300 |
| AAPL | 2026-09-03 20:00 | 327.16 | 328.73 | 327.10 | 328.22 | 174776 |
| TSLA | 2026-09-03 21:00 | 377.47 | 377.47 | 377.46 | 377.47 | 534 |

Evidências atuais:

- [SPY em retrato](evidence/m15-real-xiaomi-spy-portrait.png).
- [AAPL em retrato](evidence/m15-real-xiaomi-aapl-portrait.png).
- [TSLA em retrato](evidence/m15-real-xiaomi-tsla-portrait.png).
- [Retorno para SPY](evidence/m15-real-xiaomi-spy-return-portrait.png).
- [Comparação de API, PostgreSQL e replay](evidence/m15-real-xiaomi-api-validation.json).
- [Sequência de navegação e restauração da rotação](evidence/m15-real-xiaomi-ui-validation.json).

A sessão regular estava fechada. Replay de registros já persistidos não comprova streaming externo nem nova hora ao vivo. Essas duas validações continuam pendentes. O aplicativo ficou aberto em SPY, usando o backend Alpaca existente.

Nesta rodada somente documentação/evidências foram alteradas. O .env foi preservado; nenhum segredo foi exibido ou incorporado às evidências. Não foi necessário alterar código de produção ou testes; as suítes anteriores não foram reexecutadas como se fossem novos resultados. Build, execução física, REST/DB/replay e revisão visual foram efetivamente executados. M2/M3 não foram iniciados.

Os registros abaixo descrevem rodadas anteriores e suas pendências **à época**. A validação do Xiaomi real descrita acima substitui a pendência anterior de dispositivo offline/histórico real no tablet.

## Histórico M0

Aceite antigo em [STATUS-M0](STATUS-M0.md). Seus números de testes, revisão 0001_m0 e capturas descrevem exclusivamente M0. Não são validação atual.

## Validação M1

Evidências históricas em docs/evidence/m1-*. A integração anterior do simulador passou REST/WS e retomada após interrupção. Não comprova Alpaca. [DEMO](DEMO.md) ainda contém o roteiro histórico M1 e será revisado junto às correções.

## Validação M1.5 — diagnóstico inicial executado em 2026-09-03

| Verificação | Resultado observado |
| --- | --- |
| git status / HEAD / ls-remote | Limpo; main e remotos no commit c08ddf8 |
| Ruff check | Falhou: 46 erros |
| mypy | Falhou: 11 erros em 5 arquivos, 33 arquivos examinados |
| pytest -m "not integration", provider forçado simulator | 32 passaram; 10 PostgreSQL não executados nessa chamada |
| Flutter analyze | Falhou: 9 problemas, incluindo referências a enums removidos |
| adb devices / flutter devices | Xiaomi 23073RPBFG / 1791a20e / Android 15 detectado |
| Docker Compose ps | Engine Linux indisponível inicialmente; inicialização em diagnóstico |
| Credenciais locais | Variáveis presentes; nenhum valor exibido |
| RUN_ALPACA_SMOKE_TEST | Desabilitado; acesso real não validado nesta etapa |

Logs de diagnóstico em .artifacts/m15-baseline-*. Aviso de depreciação Starlette/AnyIO preservado, sem supressão.

Problemas confirmados por leitura: histórico ignora símbolo/timeframe; minute bars rotuladas como 1h; sequence por timestamp incompatível com cliente; ValueError ignorado; status conflitando com runtime; fixtures e documentação desatualizados. Ausência de testes dedicados suficientes ao provider.

## Plano em execução

1. Identidade de mercado separada do cursor interno consecutivo por série.
2. 1h fechado obtido da REST 1Hour; minute bars WS apenas notificam atualização.
3. Configuração, handshake, estados, calendário, backoff e falhas explícitas.
4. Persistência idempotente incluindo evento/sinal/decisão, replay e consulta por símbolo.
5. Flutter com séries independentes e testes de troca/reconexão.
6. Fakes Alpaca sem internet, PostgreSQL real, qualidade, documentação e pequenos commits.

## Validação final das correções — 2026-09-03, aproximadamente 20:06 BRT

**Código corrigido e validações locais aprovadas. M1.5 permanece em validação: dados Alpaca reais na cadeia até o tablet ainda não foram validados nesta execução.**

| Comando/verificação executada | Resultado final |
| --- | --- |
| uv sync --locked | Ambiente sincronizado, Python 3.12.10 |
| uv run ruff format; uv run ruff format --check . | 67 arquivos formatados, sem alterações pendentes |
| uv run ruff check . | All checks passed |
| uv run mypy | Sem problemas em 38 arquivos de código |
| uv run pytest -m "not integration" | 96 passaram; inclui 63 cenários dedicados do provider/smoke/configuração Alpaca com fakes |
| RUN_DB_TESTS=1; uv run pytest -m integration | 18 passaram no PostgreSQL real descartável localhost:5433 |
| ./scripts/check.ps1 -Database | Fluxo completo terminou com sucesso; 114 testes Python e 42 Flutter |
| docker compose --profile test up -d --wait postgres postgres_test | Ambos saudáveis; PostgreSQL 17.9-alpine, portas locais 5432 e 5433 |
| uv run alembic upgrade head / current / check | 0006_m15_integrity (head); nenhuma operação pendente |
| flutter pub get --enforce-lockfile | Lockfile aceito |
| dart format / verificação de formatação | lib, test, integration_test, test_driver aprovados |
| flutter analyze --fatal-infos --fatal-warnings | No issues found |
| flutter test | 42 passaram; séries independentes, recuperação, texto 1x/2x, acessibilidade e viewports |
| flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000 | APK compilado com sucesso |
| adb devices -l / flutter devices | Xiaomi 23073RPBFG, 1791a20e, Android 15/API 35, arm64 detectado |
| flutter run -d 1791a20e --no-resident --dart-define=API_BASE_URL=http://127.0.0.1:8000 | App normal compilado, instalado e aberto inicialmente |
| flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d 1791a20e --dart-define=API_BASE_URL=http://127.0.0.1:8000 | Dois cenários físicos aprovados: retrato/paisagem, REST, novo evento WS e toque na inspeção; driver inclui tearDown no contador final |
| ./scripts/capture-tablet.ps1 -Device 1791a20e -Prefix m15-tablet-simulator | Capturas revisadas em 1200×1920 e 1920×1200; display inteiro, textos legíveis, sem overflow visível |
| Reinstalação final: adb install -r .../app-debug.apk; adb shell am start | Após uma recusa do instalador e nova tentativa, Success; app normal em primeiro plano, PID observado 10173 |
| curl.exe http://127.0.0.1:8000/health | HTTP 200; status=ok, database=up, provider=simulator, state=connected |
| uv run python -m scripts.smoke_test | SKIPPED: RUN_ALPACA_SMOKE_TEST=1 required; não iniciada conexão real |
| git diff --check | Sem erros de whitespace |

Evidências atuais: [qualidade completa](evidence/m15-quality.txt), [build APK](evidence/m15-apk-build.txt), [testes no tablet](evidence/m15-tablet-tests.txt), [SQL](evidence/m15-database-check.txt), [health](evidence/m15-health.json), [retrato](evidence/m15-tablet-simulator-portrait.png), [paisagem](evidence/m15-tablet-simulator-landscape.png).

Logs completos de desenvolvimento ficam em .artifacts e não são publicados. O APK normal está em apps/mobile_app/build/app/outputs/flutter-apk/app-debug.apk. API ficou executando em loopback, com MARKET_DATA_PROVIDER=simulator sobrescrito **somente no processo de validação**, e acesso do tablet via adb reverse tcp:8000 tcp:8000. O .env existente não foi alterado.

## Integridade e preservação verificadas

- Histórico de um símbolo por chamada; apenas 1h → 1Hour validado. Minutos WS não são convertidos para horas.
- Decimal sem float na leitura JSON, UTC, margem de fechamento, rejeição de parciais e precisão incompatível com o banco.
- Identidade global provider+symbol+timeframe+open_time preservada; cursores consecutivos independentes por série.
- PostgreSQL: reimportação, duplicatas concorrentes, restart do repositório e do lifespan FastAPI, backfill repetido e replay WS preservam candle/evento/Signal/RiskDecision. Testes usam payloads fictícios e banco real, sem internet.
- SPY e AAPL no mesmo horário coexistem; duplicata do mesmo ativo não gera outro evento/sinal/risco.
- Conflito de conteúdo interrompe a ingestão e deixa log estruturado. Falha da estratégia reverte as quatro escritas sem buraco no cursor.
- Constraints candle+strategy_version, RiskDecision por Signal e is_closed testadas no PostgreSQL.
- Cenários físicos atuais usam **simulador**: retrato REST=114/WS=1/cursor=114, paisagem REST=115/WS=1/cursor=115.
- Consulta local registrada: 325 candles, 325 eventos, 325 sinais e 325 decisões, com 325 identidades de mercado distintas. É snapshot pontual; o simulador continua gerando dados.
- Quarentena preservou os **739 candles Alpaca legados**, com **739 eventos, 739 sinais e 739 decisões**. Tinham origem horária não comprovada e incluíam aberturas em minutos como 20:19/20:39. Não foram declarados dados válidos.
- Backup completo anterior à migração: .artifacts/m15-before-quarantine.sql, 540.491 bytes; ignorado no Git. Migração/rollback da quarentena testados com preservação do grafo completo no banco descartável.

## Problemas corrigidos durante esta execução

Além das falhas iniciais de lint/tipagem/Flutter, foram corrigidos fixtures desatualizados, falta de campos do contrato, referências aos enums antigos e isolamento de testes: um caso novo deixava candles Alpaca para o teste de downgrade seguinte. A limpeza agora ocorre também no encerramento da fixture do banco descartável. A sequência completa foi repetida e passou.

Docker Desktop 4.68.0 repetiu o erro de socket do Inference manager. Processos Docker e somente a distribuição WSL docker-desktop foram reiniciados. Diretórios de sockets foram preservados com sufixo .stale-20260903193627. Nenhum volume/imagem foi apagado e não houve factory reset. Detalhes em [SECURITY](SECURITY.md).

O instalador Android recusou uma reinstalação após a integração. Nova tentativa com confirmação do usuário retornou Success. Pendência antiga de instalação do M1 **não se aplica ao estado final atual**. Rotação confirmada ao terminar: free, user_rotation=0, accelerometer_rotation=1. Não houve alteração permanente de resolução, densidade ou configuração global do Flutter/SDK.

## Avisos e limites atuais

- Um aviso de depreciação vem de Starlette/AnyIO (BlockingPortal). Não foi suprimido; testes passaram.
- Build registrou aviso de versões XML do SDK Android e Flutter informou atualizações opcionais de dependências. Não alteramos SDK global nem atualizamos dependências fora do escopo; build/análise passaram.
- Logs debug da MIUI mostraram mensagens internas de fabricante; app iniciou, permaneceu ativo e passou os testes. Não foi observado crash da aplicação nem overflow Flutter.
- Não há validação atual de autenticação/feed Alpaca real, histórico real corrigido, nova hora real ao vivo ou SPY real na tela do Xiaomi. O estado market_closed foi testado com relógio/calendário controlados, não usado para fingir validação externa.
- Margem de 60 segundos não garante ausência de revisões futuras do fornecedor. Conflitos recebidos exigem investigação e não sobrescrevem decisões.
- Somente 1h, um backend/produtor, uso local em debug. Nenhuma ordem, Trading API, executor paper ou expansão de M2/M3.

## Commits locais desta correção

Branch codex/m15-data-integrity, baseada em c08ddf8. Nenhum push foi executado.

| Commit | Conteúdo |
| --- | --- |
| 82eecf6 | Diagnóstico e status em validação |
| aae3b57 | Domínio de candle fechado, contratos e configuração validada |
| 2072747 | REST horária, handshake/backoff/estados, smoke e fakes Alpaca |
| 2afe807 | Séries persistentes, idempotência, quarentena e testes PostgreSQL |
| c332f55 | Flutter por ativo, layouts e integração física |

A documentação e estas evidências são registradas no commit final de documentação.

## Próximo passo autorizado a preparar, ainda não executado

As variáveis ALPACA_API_KEY_ID e ALPACA_API_SECRET_KEY já estavam presentes localmente; seus valores não foram exibidos. Não é necessário enviá-las no chat. Caso seja preciso substituí-las, obtê-las no [painel Alpaca](https://app.alpaca.markets/) conforme a [documentação Market Data](https://docs.alpaca.markets/us/docs/market-data-faq).

Aguardar habilitação explícita de RUN_ALPACA_SMOKE_TEST=1 e seguir [RUNBOOK](RUNBOOK.md) / [DEMO](DEMO.md) para Alpaca real → SPY → PostgreSQL → REST/WS → Flutter → Xiaomi. Somente depois de evidência dessa cadeia e nova hora fechada considerar concluir M1.5. Não avançar automaticamente a M2/M3.

