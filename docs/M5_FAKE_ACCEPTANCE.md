# M5 — aceite físico da etapa FAKE

Validação em 2026-09-04, branch `codex/m5-observer`, base remota confirmada por
pull e ls-remote: `c1867db03ed33f797abf2cc8e10260a885a9223c`.
**M5 fake visual acceptance: APPROVED. Modelo real: PENDING. M6 não iniciado.**
Não é aceite do M5 completo nem de qualidade de inferência de IA.

## Ambiente e execução

Xiaomi 23073RPBFG, serial 1791a20e, Android 15/API35, detectado por `adb devices -l`
e `flutter devices`. APK debug compilado e instalado; API FastAPI real com
PostgreSQL local. Conexão exclusivamente USB/loopback:

```powershell
. ./scripts/use-android.ps1
$env:MARKET_DATA_PROVIDER = 'simulator'
$env:SIMULATOR_ENABLED = 'false'
$env:BACKTEST_ARTIFACTS_DIR = '.artifacts/m4-acceptance-reports'
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --log-config infrastructure/docker/logging.json --ws websockets-sansio
# Em outra sessão, na raiz:
. ./scripts/use-android.ps1
adb -s 1791a20e reverse tcp:8000 tcp:8000
cd apps/mobile_app
flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000
adb -s 1791a20e install -r build/app/outputs/flutter-apk/app-debug.apk
```

Coleta de mercado fica desligada para congelar Signal/Risk durante a prova.
Market mostra dados TEST já persistidos e estado degradado esperado por ausência
de streaming; isso não é falha de conexão da API Observer. Não usar provider Alpaca
nessa execução offline: seu runtime inicia coleta mesmo com SIMULATOR_ENABLED=false.
Nenhuma alteração global de Flutter/SDK, nenhuma LAN, nenhum modelo real.

## Dados FAKE persistidos

Reutilizado snapshot aprovado de 96 candles, hash
`587e58838720e85214de05203504dd6ec929592ec82023b20415f212feb9b2b8`.
Criadas três análises pela CLI do núcleo, somadas às cinco anteriores:

| Caso | analysis_id | Produção |
| --- | --- | --- |
| DISABLED | c378fe47-83b0-4913-8515-f7d736762031 | FakeProvider, sem --enabled |
| TIMEOUT | f2aff3ef-1b25-4152-a8e2-52c1631b445e | Imagem fake OCI aprovada, --enabled --timeout 0.05 |
| OK | 3800434b-af16-4c8a-9763-caa489bf29dd | FakeProvider, --enabled |

Comando-base: `uv run python -m scripts.observer analyze .artifacts/m5-snapshot.json
--analysis-id UUID`, acrescentando os parâmetros do caso. OCI usa `--image` com
ID retornado por `docker image inspect trading-bot-observer-fake:1 --format '{{.Id}}'`.
Não houve INSERT manual de conteúdo inventado no banco de uso, nem mudança no Paper
para preparar análises. Imagem aprovada:
`sha256:8c3c56c0b12bf22016d4383696838395d4694bb7fa58e0714c4a71a7413ed80a`.

Os fakes aprovados retornam UNCERTAIN/confidence 0, evidências e flags vazias.
Esses estados vazios foram exibidos e inspecionados; não foram fabricadas evidências
ou flags positivas para screenshots. Renderização de arrays preenchidos continua
coberta por widget tests. TIMEOUT/MODEL_ERROR/DISABLED mantêm auditoria DEGRADED/HOLD.
A UI identifica DISABLED pelo error_code e preserva o status original na auditoria.

## API e segurança funcional

GET status, lista e todos os oito detalhes: HTTP 200 e conteúdo conferido com as
linhas persistidas. UUID inexistente 404, inválido 422. POST/PUT/PATCH/DELETE nos três
caminhos 405; OpenAPI possui somente GET para Observer. Nenhuma rota importa/chama
provider ou inicia análise. Consultar/atualizar a tela não criou novas análises.

Somente campos públicos são serializados. Sem sanitized_input, request_hash,
credencial, .env, path local, raw stdout/stderr. Metadados são limitados aos providers
fake/OCI aprovados e versões conhecidas. Saída é revalidada pelo contrato do núcleo
e output_hash antes de qualquer resposta; corrupção retorna 503 genérico.
Erro do banco também é 503 genérico. Isso não transforma checksum em assinatura
contra um operador privilegiado; evita expor conteúdo não validado pelo HTTP.
Novo provider futuro exige evolução explícita do contrato público, fora deste aceite.

Regressões PostgreSQL plantam campo raw_stdout, path em model e erro arbitrário;
status/lista/detalhe recusam todos, sem ecoar conteúdo. Testes usam exclusivamente
127.0.0.1:5433/trading_bot_test; fixture defeituosa que apontava para 5432 foi corrigida.

Comparação integral das nove tabelas paper +signals+risk_decisions, antes dos dados
de demonstração e depois dos fluxos físicos: **todas idênticas**. Cash 9084.3458912448,
LONG TSLA 3, 1 ordem/1 fill, paused=true; 2.193 signals e 2.193 risk_decisions inalterados.
Arquivos M4 aceitos mantiveram SHA-256; não foi executado backtest. Não houve
pause/resume/reset. [Hashes antes/depois](evidence/m5-fake-acceptance.json).

## Fluxo físico e acessibilidade

Market → AI Observer → Status → Timeline → OK → Regime/Confidence → Evidências
→ Risk Flags → Observations → Auditoria → DEGRADED/HOLD → DISABLED → Paper.
Executado em retrato 1200×1920 e paisagem 1920×1200, sem janela reduzida. Repetidas
as verificações de leitura/rolagem com `font_scale=2.0` nos dois formatos.
Testes automatizados também usam `TextScaler.linear(2)` em ambos os formatos;
Android15 aplica sua política nativa de escala à fonte no teste físico.

Timeline, detalhe e auditoria roláveis, texto legível, alvos de navegação acessíveis.
Identificação OBSERVADOR/SEM AUTORIDADE DE EXECUÇÃO também no detalhe. Aviso explícito
**Observer HOLD ≠ Strategy HOLD**, sem instrução executável. DESLIGADO não afirma
que Strategy/Risk estão ativos: informa apenas que o Observer não os altera.

Sem crash/RenderFlex overflow/exceção Flutter nos 256 registros do processo final
PID 18630. Screenshot de fim da auditoria 2x comprova acesso aos hashes/status/TIMEOUT.
Fonte restaurada para 1.0 e rotação para free, os valores observados antes do teste.
APK normal permanece instalado e API/ADB reverse disponíveis em loopback.

## Screenshots físicos reais

Todos os 21 arquivos relacionados no [manifesto de aceite](evidence/m5-fake-acceptance.json)
foram capturados diretamente por `adb -s 1791a20e exec-out screencap -p`, sem edição,
mock ou geração de imagem. Manifesto inclui horário UTC, serial, resolução, escala
e hash de cada PNG. Os placeholders anteriores de timeline/detail/degraded foram
substituídos por capturas reais.

| Evidência requerida | Arquivo físico |
| --- | --- |
| Status | [m5-xiaomi-observer-status.png](evidence/m5-xiaomi-observer-status.png) |
| Timeline | [m5-xiaomi-observer-timeline.png](evidence/m5-xiaomi-observer-timeline.png) |
| Análise | [m5-xiaomi-observer-analysis.png](evidence/m5-xiaomi-observer-analysis.png) |
| Riscos e evidências vazias, 2x | [m5-xiaomi-observer-risk.png](evidence/m5-xiaomi-observer-risk.png) |
| DEGRADED/HOLD | [m5-xiaomi-observer-degraded.png](evidence/m5-xiaomi-observer-degraded.png) |
| Auditoria, 2x | [m5-xiaomi-observer-audit.png](evidence/m5-xiaomi-observer-audit.png) |
| Paisagem | [m5-xiaomi-observer-landscape.png](evidence/m5-xiaomi-observer-landscape.png) |
| Paper preservado | [m5-xiaomi-paper-preserved.png](evidence/m5-xiaomi-paper-preserved.png) |

Complementos no manifesto: DISABLED, detalhe, status/timeline/auditoria/HOLD em
paisagem 2x, status retrato 2x e Paper em ambos os formatos com 2x.

## Gates e correções

Ruff format/check OK, 120 arquivos; Mypy OK, 68 arquivos. Pytest: **282 passaram = 212
sem PostgreSQL  + 70 PostgreSQL**. Alembic check sem operações pendentes, revisão 0009.
Flutter analyze sem problemas; **83 testes passaram**; APK debug realmente compilado.
Nenhum teste desabilitado. Aviso Starlette/AnyIO preexistente; aviso SDK XML na
primeira compilação não impediu build. Logs completos locais em `.artifacts/m5-physical-*`.

Corrigidos: fixture em banco incorreto/credenciais hardcoded; resposta HTTP sem
validação do conteúdo persistido; distinção DISABLED ausente na timeline; overflow
de 33 pixels no status em paisagem 2x; ocultação de evidências vazias; data base chamada
incorretamente de última análise. SafeArea/rolagem e largura dos cards corrigem a
apresentação no dispositivo; horário de criação consta da auditoria.
Strategy, RiskEngine, PaperExecutor, Backtest Engine e providers fake não alterados.
