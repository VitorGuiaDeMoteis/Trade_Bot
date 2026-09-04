# Trading Bot Dashboard — pacote de partida

Este pacote congela o escopo da v0.1 antes da implementação. O objetivo da primeira versão é provar que o sistema consegue receber dados, processar sinais simulados, aplicar controles de risco e exibir tudo em um dashboard mobile-first, sem dinheiro real.

## Ordem de leitura

1. `PRODUCT.md` — produto, usuários, escopo e experiência.
2. `ARCHITECTURE.md` — componentes, dados, segurança e contratos.
3. `MILESTONES.md` — sequência de entregas e critérios de aceite.
4. `IMPLEMENT.md` — regras permanentes para a implementação.
5. `CODEX_START.md` — prompt inicial para abrir o projeto no Codex.

## Decisões já tomadas

- Flutter mobile-first para celular e tablet.
- Python com FastAPI no backend.
- PostgreSQL como banco principal.
- REST para consultas e WebSocket para atualizações em tempo real.
- Dados, sinais, ordens e resultados simulados na v0.1.
- Alpaca Paper Trading somente depois que a simulação local estiver estável.
- Codex/IA começa como analista, sem autoridade direta para enviar ordens.
- Nenhuma chave de corretora no aplicativo ou no processo da IA.
- Nenhum dinheiro real na v0.1.

## Definição de pronto da v0.1

Em um celular ou tablet, o usuário consegue abrir o dashboard e acompanhar candles, saldo simulado, P&L, posições, sinais, decisões do risco e status do sistema em tempo real. O sistema pode ser reiniciado sem duplicar ordens e possui um botão funcional para bloquear novas operações.

## Implementação atual: M4 — núcleo de backtesting

M3 tem carteira e executor paper local, reconciliados, com STOP pelo app e retomada
somente por CLI. O núcleo M4 acrescenta backtest offline reutilizando Strategy,
Risk e PaperExecutor, dataset congelado, replay determinístico e relatório JSON.
Migração atual: `0008_m3_paper`; nenhum acesso à Trading API.

[Executar e verificar M4](docs/M4_CORE.md) · [STATUS](docs/STATUS.md) ·
[Métricas produzidas](docs/evidence/m4-metrics.json).
Somente o núcleo M4 foi autorizado: Flutter, gráficos e replay visual permanecem
fora desta entrega, assim como IA e M5. Alpaca existente é somente Market Data;
freeze lê histórico já persistido e run não usa rede nem banco.

### Pré-requisitos

- Flutter 3.44.7 / Dart 3.12.2; Python 3.12 e [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Docker Desktop com engine Linux e Compose.
- JDK 17 ou 21, Android SDK 36, Build Tools 36.0.0, NDK 28.2.13676358; tablet USB autorizado.
- O SDK desta máquina fica em `.tools/android-sdk`. O script abaixo ajusta apenas a sessão; não altera configuração global.

### Executar no PowerShell

Na raiz:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv sync --locked
$env:MARKET_DATA_PROVIDER = 'simulator'
docker compose up -d --wait
uv run alembic upgrade head
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --log-config infrastructure/docker/logging.json --ws websockets-sansio
```

Outro terminal na raiz:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
. ./scripts/use-android.ps1
adb devices -l
flutter devices
adb -s 1791a20e reverse tcp:8000 tcp:8000
cd apps/mobile_app
flutter pub get --enforce-lockfile
flutter run -d 1791a20e --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

O serial é o Xiaomi utilizado no aceite; substitua pelo retorno de `adb devices` em outro dispositivo. Aceite o diálogo de instalação Android se solicitado. `API_BASE_URL` é obrigatório: sem ele a tela apresenta erro de configuração. Não há endereço padrão embutido no Dart. HTTP sem TLS está liberado somente no build Android de debug; o tráfego da demo usa USB. Mantenha a API em loopback.

`/health` retorna 200 com banco/migração prontos e provider conectado ou sessão regular fechada. Banco indisponível, schema pendente ou produtor parado/degradado retornam 503. A primeira leitura pode observar `starting`; aguarde o primeiro candle.

Pare qualquer backend anterior antes da migração. A revisão atual é `0006_m15_integrity`: registros Alpaca antigos de origem horária não comprovada são preservados em quarentena com seus eventos/sinais/decisões. Não são mostrados como dados horários válidos. Veja o [runbook de migração](docs/RUNBOOK.md).

### Dados reais — histórico validado; streaming ao vivo pendente

Somente Alpaca **Market Data**. `ALPACA_API_KEY_ID` e `ALPACA_API_SECRET_KEY` ficam no `.env` local; nunca no chat ou Flutter. Configure `MARKET_DATA_PROVIDER=alpaca`, feed `iex`, símbolos `SPY,AAPL,TSLA` e timeframe `1h`. A sessão PowerShell pode sobrescrever o provider do arquivo.

`uv run python -m scripts.smoke_test` retorna **SKIPPED** por padrão. Habilitar `RUN_ALPACA_SMOKE_TEST=1` é o opt-in explícito para o smoke real, com timeout de 45 s. Mercado fechado informa que streaming não foi validado. Instruções e limites em [RUNBOOK](docs/RUNBOOK.md) e [DEMO](docs/DEMO.md).

Candles 1h vêm da REST nativa `1Hour`, após fechamento + 60 s; barras WS de minuto não são rebatizadas como horas. Cada ativo tem seu cursor persistente. Duplicatas não geram outros Signal/RiskDecision; conflitos de conteúdo falham explicitamente. Nenhuma ordem é criada.

### Verificar

```powershell
# Raiz; SDK/Flutter disponíveis na sessão
./scripts/check.ps1 -Database
# apps/mobile_app
flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000
flutter drive -d 1791a20e --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=CAPTURE_SCREENSHOTS=true
```

Para testar a interrupção real, acrescente `--dart-define=RUN_RECONNECT_TEST=true` e siga os marcadores descritos no [RUNBOOK](docs/RUNBOOK.md). Esse cenário precisa da parada/reinício controlados do backend em outro terminal.

### Estrutura principal

```text
apps/mobile_app/lib/src/market/     API, contratos Dart, conexão e gráfico
services/api/                      REST, WebSocket, persistência e runtime
services/market_simulator/          Gerador puro determinístico
services/market_data/               Adapters simulator/Alpaca Market Data
services/strategy_engine/           BaseStrategy existente, análise simulada
services/risk_engine/               RiskEngine existente, decisão simulada
services/paper_executor/            Fronteira reservada, sem executor
packages/domain/                   Candle, invariantes e relógio virtual
packages/contracts/                Saúde 1.1, snapshot/eventos 2.0
infrastructure/docker/migrations/   Cadeia até 0006_m15_integrity
infrastructure/docker/logging.json  Logs JSON
scripts/                           Qualidade, SDK por sessão e captura
tests/                            Testes Python, fronteiras e PostgreSQL
docs/                             Status, decisões, runbook, segurança, demo
docker-compose.yml                PostgreSQL dev e banco isolado de testes
.env.example                      Somente valores fictícios
pyproject.toml / uv.lock           Python 3.12 e dependências fixadas
```

Veja [STATUS](docs/STATUS.md), [DECISIONS](docs/DECISIONS.md), [SECURITY](docs/SECURITY.md), [DEMO](docs/DEMO.md) e os [contratos atuais](docs/CONTRACTS.md). M0 e M1 possuem registros históricos separados. A visão completa v0.1 acima descreve etapas futuras: ordens, carteira, IA e M2/M3 não estão autorizados nesta correção.
