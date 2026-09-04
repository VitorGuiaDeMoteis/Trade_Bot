# M4 — aceite final API/Flutter/Xiaomi

**APPROVED em 2026-09-04**, após validação física e gates completos.
Base recebida por pull: `de7b84a2578e04f0f41cabb1165dcd58d7b5fbd4`, branch
`codex/m4-backtesting`. [Resultados, bugs e contagens](STATUS.md).
Sem mudança de Strategy/Risk/PaperExecutor/núcleo, sem otimização, merge ou M5.

## Executar localmente

PowerShell, raiz do repositório, dependências e `.env` local já preparados.
O relatório precisa existir: para gerá-lo use [M4_CORE](M4_CORE.md#executar-no-powershell).
Não colocar relatórios no APK nem transferi-los manualmente ao tablet.

```powershell
uv sync --locked
docker compose up -d --wait postgres
uv run alembic upgrade head
New-Item -ItemType Directory -Force .artifacts/m4-acceptance-reports
Copy-Item .artifacts/m4-report.json .artifacts/m4-acceptance-reports/report.json
$env:BACKTEST_ARTIFACTS_DIR = '.artifacts/m4-acceptance-reports'
$env:SIMULATOR_ENABLED = 'false'
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --log-config infrastructure/docker/logging.json
```

Executar apenas um backend por porta. `SIMULATOR_ENABLED=false` mantém coleta
desligada durante a inspeção dos relatórios e do histórico já persistido. Não
retomar/resetar paper. A disponibilidade de streaming não é requisito para ler
um backtest congelado; M1.5 em sessão aberta permanece pendente.

Outro terminal na raiz:

```powershell
. ./scripts/use-android.ps1
adb devices -l
flutter devices
adb -s 1791a20e reverse tcp:8000 tcp:8000
adb -s 1791a20e reverse --list
cd apps/mobile_app
flutter analyze
flutter test
flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000
adb -s 1791a20e install -r build/app/outputs/flutter-apk/app-debug.apk
adb -s 1791a20e shell am start -n dev.tradingbot.mobile_app/.MainActivity
```

O SDK é ajustado somente na sessão. O tráfego do Xiaomi percorre o túnel USB;
nenhum listener na LAN foi criado. APK final SHA-256:
`b49bfc8d4d43fa034043f5708fd2a1fbc76deb1aad8428845fe4860e679b3104`.

## API real

```powershell
$reports = Invoke-RestMethod http://127.0.0.1:8000/api/v1/backtests
$resultHash = $reports[0].result_hash
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/backtests/$resultHash"
Invoke-WebRequest "http://127.0.0.1:8000/api/v1/backtests/$resultHash/export" -OutFile .artifacts/export.json
```

Listagem/detalhe/export validados contra o mesmo relatório original. Exportação
com `Content-Disposition: attachment` devolve o objeto já validado em memória.
Campos consumidos no Flutter são validados sem refazer P&L, métricas ou saldo.
Relatórios inválidos não entram na lista nem podem ser baixados; consulta por
hash inexistente retorna 404. Ausência de POST/PUT/DELETE de execução confirmada
por 405 nos três caminhos. Traversal e arquivo fora da pasta configurada: 404.

O teste de confinamento modela um symlink por seu caminho resolvido, sem depender
de privilégio de administrador no Windows (criação real negada com código 1314).
O teste de export troca o arquivo após validação para provar que a resposta não
reabre conteúdo substituído. Arquivo externo real, JSON corrompido, hashes e
métodos HTTP também foram verificados no Uvicorn real ligado ao PostgreSQL dev.

## Qualidade

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
docker compose --profile test up -d --wait postgres_test
$env:RUN_DB_TESTS = '1'
uv run pytest -q
uv run pytest --collect-only -q -m integration
```

Resultado: **172 testes sem PostgreSQL + 49 PostgreSQL = 221 Python**, **75 Flutter**.
Nenhum teste removido/desabilitado. Ruff format/check, mypy, Flutter analyze e
APK debug passaram. Testes DB usam exclusivamente o banco descartável em 5433.
Para checar Alembic nele, usar outro terminal:

```powershell
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_PORT = '5433'
$env:POSTGRES_DB = 'trading_bot_test'
$env:POSTGRES_USER = 'test_only'
$env:POSTGRES_PASSWORD = 'test_only'
uv run alembic check
```

Resultado: `No new upgrade operations detected`. Nenhuma migração nova.

## Fluxo físico e evidências

Xiaomi 23073RPBFG, serial 1791a20e, Android 15/API35. Portrait 1200×1920 e
landscape 1920×1200, sem janela reduzida. Rotação forçada temporariamente via
`wm user-rotation lock 0/1`, restaurada a `free`, valor 0. Não foi alterado o SDK.

Em ambas as orientações: Market → Backtest → lista → Summary → Curva (toque e
arraste) → Trades → Replay → próximo → anterior → fim → início → export → Paper.
Detalhes dos trades são exibidos diretamente nos cards, sem modal adicional.
Campos inspecionados contra JSON: quantidade, horários, fees, P&L e classificação.
Replay associa cada fill no OPEN ao snapshot do CLOSE daquele candle de 1h.
Os botões têm 48 dp e ficam acima da navegação Android após a correção SafeArea.
Listas/estado usam rolagem quando a altura é menor em paisagem.

Dois downloads concluídos no Chrome pelo botão do app, com origem
`127.0.0.1:8000`. Arquivos em `/sdcard/Download`, recuperados por `adb pull` e
comparados integralmente como JSON ao relatório original: iguais em ambas as
orientações. Essa comparação admite diferenças de espaços/UTF-8 entre serializers,
mas exige os mesmos campos, valores e `result_hash`.

O processo Flutter permaneceu sem crash, overflow ou exceção no logcat do fluxo
final (266 linhas). A carteira atual manteve todas as tabelas idênticas e pausadas:
TSLA 3, cash 9084.3458912448 USD, 1 ordem e 1 fill. O backend ficou disponível em
loopback; o aplicativo normal permaneceu instalado e retornou à carteira pausada.

- [Summary portrait](evidence/m4-xiaomi-summary.png)
- [Equity portrait](evidence/m4-xiaomi-equity.png)
- [Trades portrait](evidence/m4-xiaomi-trades.png)
- [Replay portrait](evidence/m4-xiaomi-replay.png)
- [Summary landscape](evidence/m4-xiaomi-landscape.png)
- [Equity landscape](evidence/m4-xiaomi-equity-landscape.png)
- [Trades landscape](evidence/m4-xiaomi-trades-landscape.png)
- [Replay landscape](evidence/m4-xiaomi-replay-landscape.png)
- [Export portrait](evidence/m4-xiaomi-export.png)
- [Export landscape](evidence/m4-xiaomi-export-landscape.png)
- [Separação do Paper pausado](evidence/m4-xiaomi-paper-separation.png)
- [Recibo de aceite, hashes e contagens](evidence/m4-acceptance.json)

Os logs brutos e os JSON completos permanecem em `.artifacts` fora do Git.
M5 NÃO iniciado. M1.5 streaming Alpaca em sessão aberta ainda pendente.
