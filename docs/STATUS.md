# Status — Trading Bot Dashboard v0.1

## M1.5 — em validação

Base: main, c08ddf87216efb2e09bea55e497ec6439392d8ef. Checkout inicialmente limpo. Remoto informado pelo usuário e origin atual resolveram para o mesmo commit. Correções autorizadas: dados reais + análise/decisão simulada. Sem Trading API, ordens, executor paper ou avanço de marco.

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
