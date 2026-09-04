# Aceite final M4 — 2026-09-04

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
