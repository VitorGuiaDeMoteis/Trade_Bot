# Execução e recuperação — M2 / M1.5

Comandos PowerShell, a partir da raiz salvo indicação. Simulador não exige credencial externa. Alpaca exige chaves locais e autorização explícita do teste real. Nunca executar dois backends/produtores ao mesmo tempo.

## Preparar banco e API

    if (-not (Test-Path .env)) { Copy-Item .env.example .env }
    uv sync --locked
    $env:MARKET_DATA_PROVIDER = 'simulator'
    docker compose config --quiet
    docker compose up -d --wait
    uv run alembic upgrade head
    uv run alembic current
    uv run alembic check
    uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-access-log --log-config infrastructure/docker/logging.json --ws websockets-sansio

Revisão esperada 0007_m2_decisions; tabelas alembic_version, candles, system_events, signals, risk_decisions e legacy_market_archive. Pare o backend anterior antes de migrar. Migração explícita antes do servidor, não por worker. PostgreSQL 17 com timezone UTC. Não renomear o projeto Compose trading-bot-m0: nome preservado para reutilizar o volume do M0.

## Consultar Decisions

No ambiente já autorizado com histórico real, iniciar o backend com `$env:MARKET_DATA_PROVIDER = 'alpaca'` e as chaves locais existentes, sem copiá-las para o app ou comandos. Para usar apenas dados fictícios, manter simulator. Não rodar dois produtores.

    curl.exe 'http://127.0.0.1:8000/api/v1/decisions?symbol=SPY&timeframe=1h&limit=50'

No Flutter: Decisões → selecionar ativo → rolar → tocar no cartão → voltar. Atualizar consulta busca novamente as últimas 50; contagens se referem somente à janela exibida. Offline pode preservar a última consulta com aviso; trocar ativo limpa dados anteriores. Em simulator o ativo é TEST, não SPY/AAPL/TSLA.

Antes de aplicar 0007 em outro banco, parar o backend e fazer pg_dump. A migração adiciona apenas reason e preserva o grafo; não dispara motores. O downgrade para 0006 remove esse campo e suas justificativas, portanto requer backup; não executá-lo como recuperação automática. Testes de downgrade ocorrem somente no banco descartável 5433.

A migração 0006 preserva o grafo Alpaca legado em quarentena porque misturava horas/minutos. Não expõe esse conteúdo na API. Foi feito backup local em .artifacts/m15-before-quarantine.sql. Em outro ambiente, faça backup antes de migrar. Downgrade com novos candles Alpaca falha deliberadamente: exporte e planeje a reversão, sem apagar dados para contornar.

Pré-requisitos: Flutter 3.44.7/Dart 3.12.2, Python 3.12, uv e Docker Desktop Linux. Se faltar uv: py -3.12 -m pip install --user uv. Se faltar Python 3.12: winget install --id Python.Python.3.12 -e. O projeto usa .venv; não mudar Python padrão.

Outro terminal:

    curl.exe -i http://127.0.0.1:8000/health
    $page = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/market/candles?limit=3'
    $page | ConvertTo-Json -Depth 6

| Resultado | Diagnóstico/ação |
| --- | --- |
| 200, up/connected | Banco, schema e provider operacionais |
| 200, up/market_closed | Sessão regular fechada; não é falha |
| 503, configuration_error | Corrigir chaves/feed/assinatura localmente |
| 503, reconnecting ou delayed | Ver código controlado do provider; aguardar backoff/fechamento |
| 503, schema_pending | Aplicar alembic upgrade head |
| 503, down/degraded | Ver Compose, porta e configuração local |
| 503, stopped | SIMULATOR_ENABLED=false |
| 503, starting | Aguardar primeiro commit |
| 503, stalled | Ver logs do produtor; sem progresso recente |
| Não conecta | Ver terminal Uvicorn e porta |

PowerShell 7 aceita Invoke-WebRequest -SkipHttpErrorCheck para ler 503; em 5.1 usar curl.exe. Não registrar DSN/senha. [CONTRACTS](CONTRACTS.md) detalha envelopes, versões e erros.

## Android e USB

Na raiz:

    . ./scripts/use-android.ps1
    adb devices -l
    flutter devices
    flutter doctor -v
    adb -s 1791a20e reverse tcp:8000 tcp:8000
    adb -s 1791a20e reverse --list
    cd apps/mobile_app
    flutter pub get --enforce-lockfile
    flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000
    flutter run -d 1791a20e --dart-define=API_BASE_URL=http://127.0.0.1:8000

Serial observado: Xiaomi 23073RPBFG, Android 15, 1791a20e. Substituir pelo serial detectado em outra máquina. Autorizar USB/instalação no próprio tablet se solicitado.

API_BASE_URL é obrigatório e contém somente origem http/https, sem credenciais/caminho/query/fragmento. WS deriva ws/wss da mesma origem. Não existe host padrão no Dart. HTTP está liberado apenas em debug Android; API permanece em loopback.

Repetir adb reverse após reconectar dispositivo/ADB. Para encerrar apenas esse encaminhamento: adb -s 1791a20e reverse --remove tcp:8000.

APK normal em apps/mobile_app/build/app/outputs/flutter-apk/app-debug.apk. O artefato de integração é temporário; depois de flutter drive, rodar flutter run para instalar a aplicação normal.

### SDK local ausente em outro checkout

JDK 17/21 requerido. Obter Command line tools only / Windows no [Android oficial](https://developer.android.com/studio#command-tools), verificar SHA-256 e extrair em .tools/android-sdk/cmdline-tools/latest, com bin dentro de latest. Depois:

    $sdkRoot = (Resolve-Path .tools/android-sdk).Path
    & ./.tools/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat --sdk_root=$sdkRoot --licenses
    & ./.tools/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat --sdk_root=$sdkRoot 'platform-tools' 'platforms;android-36' 'build-tools;36.0.0' 'ndk;28.2.13676358'
    . ./scripts/use-android.ps1

Responsável deve revisar/aceitar licenças. Usuário autorizou instalação/aceite nesta máquina durante M0. Gradle pode instalar CMake 3.22.1 no SDK local. Não usar setx ou flutter config para alterar preferências globais.

## Simulador

Configuração local em .env; reiniciar backend após alterar:

    SIMULATOR_ENABLED=true
    SIMULATOR_SEED=42
    SIMULATOR_START=2026-01-01T00:00:00Z
    SIMULATOR_INTERVAL_SECONDS=2

Start UTC no início de hora. Intervalo de 0,1 a 3600 segundos: 2 demonstra modo acelerado; 3600 modo normal. Cada avanço fecha uma hora virtual. Regimes em blocos de 24 candles. Ritmo não muda dados; seed/início mudam stream. Paradas congelam relógio virtual, sem backfill de tempo real.

Um único worker/produtor. Não usar --workers >1 nem múltiplos servidores para o mesmo stream. Histórico é mantido no banco; não há limpeza automática. Cliente guarda até 2.000 e desenha últimos 60. Desativar simulador deixa histórico disponível com saúde 503/stopped. Não há endpoint de controle. Alterar apenas seed no mesmo início virtual pode conflitar com a identidade global; para outra simulação, use também outro início UTC.

## Alpaca Market Data — habilitar somente na etapa autorizada

Obtenha ALPACA_API_KEY_ID e ALPACA_API_SECRET_KEY no [painel Alpaca](https://app.alpaca.markets/), seguindo a [documentação Market Data](https://docs.alpaca.markets/us/docs/market-data-faq). Permissões dependem do feed/plano. Não enviar chaves no chat nem incluir no aplicativo.

No .env local:

    MARKET_DATA_PROVIDER=alpaca
    ALPACA_API_KEY_ID=<preencher somente localmente>
    ALPACA_API_SECRET_KEY=<preencher somente localmente>
    ALPACA_DATA_FEED=iex
    MARKET_SYMBOLS=SPY,AAPL,TSLA
    MARKET_TIMEFRAME=1h
    RUN_ALPACA_SMOKE_TEST=1

Variáveis da sessão prevalecem sobre .env. Se esta sessão foi usada para simulação, alterar explicitamente o provider:

    $env:MARKET_DATA_PROVIDER = 'alpaca'
    uv run python -m scripts.smoke_test

Sem opt-in a saída é SKIPPED. Com opt-in, timeout global de 45 s, histórico SPY, provider/UTC/Decimal/fechamento e, se sessão regular aberta, handshake WS. Sessão fechada informa market_closed / streaming not validated. O smoke não persiste dados nem comprova nova hora ao vivo.

Após smoke, iniciar o único Uvicorn pelo comando acima. Consultar:

    Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/market/candles?symbol=SPY&timeframe=1h'
    Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/market/candles?symbol=AAPL&timeframe=1h'

Somente REST 1Hour fechada é persistida; WS de minuto não vira hora. Refresh a cada 60 s e catch-up paginado ao iniciar/reconectar. Conflito de conteúdo interrompe ingestão em degraded; não apagar candles nem repetir decisões para esconder a divergência. Veja [CONTRACTS](CONTRACTS.md).

O seletor só aparece com os ativos do provider do backend. Em simulator mostra TEST; em alpaca mostra os símbolos configurados. Nunca alimentar o banco de desenvolvimento com fixtures para fingir mercado real.

## Qualidade

Na raiz com SDK/Flutter na sessão:

    ./scripts/check.ps1 -Database

Equivalente backend:

    uv run ruff format .
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    docker compose --profile test up -d --wait postgres_test
    $env:RUN_DB_TESTS = '1'
    uv run pytest
    Remove-Item Env:RUN_DB_TESTS

Sem RUN_DB_TESTS=1, testes PostgreSQL são pulados; aceite exige execução explícita. Migrações repetidas, downgrade/upgrade e truncamento apenas no banco fixo trading_bot_test, porta 5433. Falha de banco não vira sucesso.

Em apps/mobile_app:

    dart format lib test integration_test test_driver
    dart format --output=none --set-exit-if-changed lib test integration_test test_driver
    flutter analyze --fatal-infos --fatal-warnings
    flutter test

## Tablet e transporte real com dados simulados

Backend/banco ativos e adb reverse configurado. Em apps/mobile_app:

    flutter drive -d 1791a20e --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=CAPTURE_SCREENSHOTS=true --dart-define=RUN_RECONNECT_TEST=true

O teste de orientação exige provider=simulator e novos candles acelerados. Não usá-lo como prova de streaming Alpaca. A aprovação de cada orientação registra M15_SIMULATOR_TABLET_PASS.

1. Esperar M1_RECONNECT_READY.
2. Ctrl+C no terminal **deste backend**.
3. Esperar M1_OFFLINE_OBSERVED; gráfico permanece visível.
4. Reiniciar backend com mesmo comando/configuração.
5. Aguardar M1_RECONNECT_PASS e testes aprovados.

Até 120 s para cada intervenção. Teste exige novos candles por REST, segunda conexão, continuidade e IDs/tempos únicos. Sem intervenção há timeout. Omitir RUN_RECONNECT_TEST para somente os dois testes de orientação/REST/WS/inspeção.

Imagens em .artifacts/m1-tablet-integration-portrait.png, landscape, offline e recovered. Driver salva bytes; revisão visual é separada.

Android pode mostrar retrato em janela de compatibilidade quando fisicamente em paisagem. Preferir girar o tablet. Se impossível, com app normal aberto, executar na raiz:

    ./scripts/capture-tablet.ps1 -Device 1791a20e -Prefix m15-tablet-simulator

Script exige o app em primeiro plano, captura display completo em retrato/paisagem e restaura modo/rotação anteriores em finally; não altera resolução/densidade. Prefixo evita sobrescrever evidência anterior.

## Falha real do PostgreSQL

Manter backend ativo:

    try {
      docker compose stop postgres
      Start-Sleep -Seconds 3
      curl.exe -i http://127.0.0.1:8000/health
      curl.exe -i http://127.0.0.1:8000/api/v1/market/candles
    } finally {
      docker compose up -d --wait postgres
    }
    curl.exe -i http://127.0.0.1:8000/health

Durante falha: 503 e simulador degraded. Após próxima tentativa: 200/connected. Não resetar banco.

Conferência SQL:

    docker compose exec -T postgres psql -U trading_bot_dev -d trading_bot_dev -c 'SELECT count(*), count(DISTINCT candle_id), count(DISTINCT (stream_id, sequence)), count(DISTINCT (stream_id, open_time)) FROM candles; SELECT count(*) FROM system_events;'

Contagens crescem com a demo. Para comparar conteúdo anterior ao reinício, salvar snapshot e seu cursor; consultar depois after=0&through=cursor_salvo&limit=500, paginando se necessário. Comparar IDs, OHLCV e timestamps.

## Parar e recuperar

Backend: Ctrl+C. Banco: docker compose stop postgres; retomar com docker compose up -d --wait postgres. Down sem --volumes preserva dados. Não remover volume como recuperação automática. Downgrade M1 remove candles/eventos e deve ficar restrito a teste descartável ou reset conscientemente autorizado.

INSTALL_FAILED_USER_RESTRICTED / Install canceled by user: instalador Android recusou. Confirmar instalação no aparelho ao repetir flutter run. Não desativar proteções para contornar.

Docker 4.68.0 teve sockets NTFS inacessíveis no M0. A recuperação preservou diretórios de sockets como .stale, listados em [SECURITY](SECURITY.md) e [STATUS-M0](STATUS-M0.md). Não apagar diretórios preservados, imagens ou volumes. Não usar factory reset como primeira tentativa. Se voltar, inspecionar logs e considerar reinício/atualização com o usuário; [incidente Docker correspondente](https://github.com/docker/desktop-feedback/issues/460).
