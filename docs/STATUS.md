# M5 — aceite do núcleo Observer, 2026-09-04

M4 ✅
M5 Core Observer ✅
M5 API ✅
M5 Flutter ✅
M5 Fake Validation ✅
M5 Real Model ⏳
M6 NÃO iniciado

**M5 core acceptance: APPROVED.** Somente o núcleo autorizado; não declarar M5
inteiro concluído. Base `bc942b046d7f9f3961f4fe0352492d8849897613` confirmada após
`git pull --ff-only origin codex/m4-backtesting`. Branch criada `codex/m5-observer`.
Nenhum merge. [Contratos, operação e limites](M5_CORE.md), [threat model](M5_THREAT_MODEL.md).

## Gates finais do M5

| Comando/validação | Resultado |
| --- | --- |
| `uv run ruff format --check .` | OK, 118 arquivos |
| `uv run ruff check .` | OK |
| `uv run mypy` | OK, 67 arquivos |
| `uv run mypy scripts/observer.py` | OK, CLI adicional |
| `docker compose --profile test up -d --wait postgres_test` | Healthy, PostgreSQL dedicado 127.0.0.1:5433 |
| `$env:RUN_DB_TESTS='1'; uv run pytest -q` | **277 passaram**, nenhum skip/failure |
| Não-PostgreSQL | **212 passaram** |
| PostgreSQL | **65 passaram**, contagem confirmada com `pytest --collect-only -q -m integration` |
| Testes adicionados M5 | **56**: 40 sem PG +16 com PG; 221 anteriores preservados |
| `uv run alembic check` | OK em dev5432 e test5433, revisão0009_m5_observer |
| Migração/reversão | Upgrade/downgrade no banco descartável; upgrade local após backup |
| OCI real | Fake OK; timeout/HOLD persistido; sem contêiner residual |
| `/health` após migração | HTTP200, database=up; API em 127.0.0.1 |
| Flutter/Xiaomi | Não executados: fora deste recorte, M4 físico já aceito |

Execução final Python: 29,59s. Único aviso: depreciação Starlette/AnyIO preexistente.
Nenhum teste desabilitado, cobertura reduzida ou tecnologia substituída. Logs
completos locais `.artifacts/m5-pytest-final.txt`, JUnit `.artifacts/m5-python-final.xml`.

## Evidências de segurança e integridade

- Projeção explícita e JSON Schemas versionados; input até64KiB, stdout16KiB,
  stderr4KiB descartado. UTC/as_of, closed candles, ordenação cross-asset e hash.
- Testes de JSON inválido/truncado, texto fora do JSON, extras, enum/confidence,
  ordens, Unicode, excesso de dados, stale/degraded/disabled e processo ausente.
- Segredos plantados em configuração, campos extras, ambiente e exceções não
  chegam ao DTO/provider/auditoria. Configuração específica DB não carrega Alpaca.
- Guards AST para imports/calls proibidos. Strategy, RiskEngine, PaperExecutor,
  Backtest Engine, domínio financeiro e Flutter sem alterações em relação à base.
- PostgreSQL compara todas as tabelas paper e também sinais/risco antes/depois
  de análise OK, falhas e disabled; nenhuma mudança. Concorrência/restart não
  duplicam análise, conflito de UUID é explícito, rollback não deixa linha parcial.
- Modelo OCI real: UID65534, rootfs read-only, somente loopback interno, sem acesso
  ao PostgreSQL, repositório ou socket Docker, capabilities zero, seccomp ativo.
  [Evidência](evidence/m5-isolation.json). Não há credenciais, vendor/SDK ou Trading API.

## Banco local e demonstração

Backup `.artifacts/m5-before.sql`, 3.435.026 bytes, ignorado pelo Git. A migração
adicionou somente auditoria independente, sem FK/trigger financeiro.
Snapshot histórico real: 96candles/21.468bytes, input hash
`587e58838720e85214de05203504dd6ec929592ec82023b20415f212feb9b2b8`.
Não retrodatamos os sinais/risco: posteriores ao as_of escolhido foram omitidos.

Fake OK, retry em novo processo sem duplicação, disabled/HOLD, OCI OK, timeout
OCI/HOLD e imagem inexistente/HOLD produziram cinco análises persistidas.
[Metadados de auditoria](evidence/m5-audit.json) e [passos da demo](DEMO.md).

Todas as linhas das nove tabelas paper ficaram idênticas antes/depois. Fingerprint
M5 `8536831e37779b86f74bf23a88a31a9f0f88cb557fa8eeba4085b42ba10f4c4a` usa lista
ordenada de JSONs de linhas (serialização diferente da evidência M4 abaixo).
Cash **9084.3458912448**, LONG **TSLA3**, **1order/1fill**, **paused=true**.
Nenhum resume/reset ou nova ordem. Snapshot e backup completos não foram publicados.

## Correções e limitações

Durante a implementação, corrigidos: seleção de último risco independente do
último sinal; runtime não instalado entrando no fallback persistido; NaN/infinito
no timeout sendo tratados como INVALID_TIMEOUT antes da inferência. JSONB ausente
usa SQL NULL para as constraints de status. Ajustadas fixtures para timestamps
históricos explícitos e normalização do ambiente Windows em uppercase.
Nenhum bug exigiu alteração no domínio financeiro aceito.

Somente fake determinístico implementado; o transporte OCI prepara o boundary de
modelo real, mas não configura Codex SDK, OpenAI ou Ollama. Docker/kernel/imagem
e operador são confiáveis. Falha do DB impede persistência; CLI falha explicitamente.
Crash pré-commit pode repetir inferência, mas não duplica uma análise persistida.
Espera por lock expira em3s; retry usa mesmo UUID. Limpeza de contêiner acrescenta
até3s ao deadline e depende do daemon. Não existe endpoint ou consumidor financeiro M5.

API reiniciada apenas para `/health` e encerrada após a prova. Observado no runtime
existente: `SIMULATOR_ENABLED=false` não desliga Alpaca quando esse provider está
selecionado; não iniciar API para a CLI offline. Isso foi documentado sem alterar
o runtime. Backend permanece restrito a loopback quando iniciado. M1.5 streaming
Alpaca em sessão aberta continua pendente; nenhum aceite desse teste foi realizado.

---

# Registro histórico: aceite final M4 — 2026-09-04

M3 ✅

M4 Core ✅
M4 API ✅
M4 Flutter ✅
M4 Replay ✅
M4 Export ✅
M4 Xiaomi ✅
M4 Acceptance ✅

M1.5 streaming Alpaca em sessão aberta ⏳
M5 NÃO iniciado

**M4 acceptance: APPROVED**, após os gates e a validação física abaixo.
Branch `codex/m4-backtesting`. `git pull --ff-only origin codex/m4-backtesting`
confirmou exatamente `de7b84a2578e04f0f41cabb1165dcd58d7b5fbd4`, também observado
em `git ls-remote`. Sem merge, otimização ou alterações no núcleo, Strategy,
Risk ou PaperExecutor. A declaração anterior de conclusão antecipada foi retirada.

## Gates finais

| Comando | Resultado |
| --- | --- |
| `uv run ruff format --check .` | OK, 99 arquivos |
| `uv run ruff check .` | OK |
| `uv run mypy` | OK, 56 arquivos |
| `docker compose --profile test up -d --wait postgres_test` | Healthy |
| `$env:RUN_DB_TESTS='1'; uv run pytest -q` | **221 passaram** |
| Não-PostgreSQL | **172 passaram** |
| PostgreSQL dedicado 5433 | **49 passaram** |
| `uv run alembic check` | Nenhuma alteração, revisão 0008_m3_paper |
| `flutter analyze` | Nenhum problema |
| `flutter test` | **75 passaram** |
| `flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000` | APK compilado e instalado |

Nenhum teste desabilitado nem cobertura reduzida. 13 casos Python e 3 testes
Flutter de regressão adicionados. Falhas reproduzidas antes das correções foram
resolvidas e os gates repetidos. Avisos de terceiros Starlette/AnyIO e SDK XML
na primeira compilação não impediram validação. Docker permaneceu funcional.

## Conexão e dispositivo

Backend **127.0.0.1:8000**, Uvicorn com `--no-proxy-headers`, sem exposição LAN.
Xiaomi **23073RPBFG / 1791a20e / Android 15 API35**, confirmado por `adb devices -l`
e `flutter devices`. `adb -s 1791a20e reverse tcp:8000 tcp:8000`, confirmado
por `reverse --list`. APK usa `API_BASE_URL=http://127.0.0.1:8000`.

Portrait **1200×1920** e landscape **1920×1200**, tela inteira. Rotação imposta
apenas durante a prova por `wm user-rotation`, restaurada a `free`, valor 0.
SDK/Flutter globais não foram alterados. App normal permanece instalado.

Nos dois formatos: Market → Backtest → lista → Summary → Equity Curve (toque e
arraste) → Trades (detalhes visíveis no próprio card) → Replay (próximo, anterior,
início, fim) → Exportar → retorno ao Paper. Não existe tela separada de trade;
BUY/SELL, horários, quantidade, fees e P&L foram inspecionados nos cards existentes.
Texto e curva legíveis, sem crash, RenderFlex overflow ou exceção Flutter nos
**266 registros de logcat do processo** durante o fluxo final.

Replay: passos 1 → 2 → 1 → 230 → 1, em ambas as orientações. O passo 2 mostra
TSLA FILLED, quantidade 3, preço de referência 305.035 e cash 9084.3458912448,
coerentes com o relatório. Toque/arraste na curva selecionaram #62/#156 em retrato
e #146 em paisagem. Há **230 frames cross-asset**, não 200; 200 é o número de
candles por ativo. Nenhuma métrica financeira é recalculada pelo Flutter.

Exportação real: Chrome mostrou Download concluído para
`trade-bot-backtest-72bd0c1c.json` e `trade-bot-backtest-72bd0c1c (1).json` em
`/sdcard/Download`. Ambos copiados por ADB e comparados como JSON integral ao
relatório original: **idênticos**, inclusive hash e todos os valores monetários.
Não foi necessário abrir backend na LAN ou copiar relatórios manualmente ao tablet.

## API, integridade e segurança

GET lista, detalhe e export: **200**, conteúdo igual ao relatório original.
Hash inexistente, arquivo fora da pasta configurada e path traversal: **404**.
Arquivo corrompido ignorado na listagem e não servido; POST/PUT/DELETE nos três
caminhos: **405**. Verificações repetidas no servidor real após a correção final.
Relatório `72bd0c1cb7ecaa12c5abb5f928cb9d803aeaea4bd7dfe24ddfa35dbe747db0d3`
permanece Source of Truth. Não há chamadas externas de Trading API.

As tabelas paper ficaram integralmente idênticas antes/depois da API e dos fluxos
físicos: hash `4683dd6e623225ec619e316dbd845d005ec5787dc9e6682447e2cd525dcec614`.
Cash **9084.3458912448 USD**, LONG **TSLA 3**, **1 ordem / 1 fill**, **paused=true**.
A tela Paper mostra SIMULAÇÃO PAUSADA e permanece distinta de BACKTEST HISTÓRICO.
Nenhum resume/reset foi executado. Provider mantido sem coleta (`SIMULATOR_ENABLED=false`)
para esta validação de relatórios locais; não houve teste de streaming em sessão aberta.

## Bugs encontrados e corrigidos

1. API seguia arquivo cujo caminho resolvido saía da pasta configurada: filtragem
   de caminho resolvido e symlinks. Regressão portável modela resolução de link;
   criação real de symlink Windows exigiria privilégio 1314, não concedido.
   Arquivo externo real e traversal também foram testados no HTTP local.
2. Export reabria arquivo após validar: agora entrega o snapshot validado em memória,
   com Content-Disposition attachment. Teste troca o arquivo entre validação e resposta.
3. JSON com checksum correto mas contrato incompleto causava erro 500/erro no Flutter:
   validação de metadados, seções, campos consumidos, hashes, datas e strings Decimal,
   sem recalcular contas. Casos incompletos, float e frames inválidos rejeitados.
4. Replay associava execução no OPEN ao frame anterior (CLOSE de mesmo horário):
   associação corrigida ao próprio candle de 1h; teste contra fixture do núcleo.
5. Replay de dataset vazio causava RangeError: agora mostra estado vazio explícito.
6. Barra Android cobria controles de replay: SafeArea e regressão com inset de 48 px.
7. Painter duplicava cálculo de drawdown: sombreado usa o drawdown do relatório;
   conversões para double ficam apenas em cor/coordenadas de desenho.

## Evidências e execução

[Screenshots e hashes do aceite](evidence/m4-acceptance.json).
[Runbook completo](M4_ACCEPTANCE.md). [Contrato do núcleo e métricas](M4_CORE.md).
Logs locais: `.artifacts/m4-acceptance-{python,flutter,analyze,build,logcat}.txt`;
reproduções anteriores em `.artifacts/m4-*-before.txt`. Artefatos de banco e
JSON completos continuam fora do Git. Apenas evidências sem credenciais versionadas.

Não existem bloqueios pendentes do M4. M1.5 streaming em sessão aberta segue
pendente; M5 não foi iniciado e depende de nova autorização.
