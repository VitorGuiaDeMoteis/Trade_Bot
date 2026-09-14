# Trade Bot Mission Control

Página desktop em HTML/CSS/JavaScript vanilla, servida pelo FastAPI em
<http://127.0.0.1:8000/mission-control>. Nenhuma dependência de frontend.

## Iniciar nesta máquina

Na raiz do repositório:

```bash
./scripts/start-mission-control.sh --isolated
```

O PostgreSQL portátil já foi preparado em `.tools/mission-control/postgres`.
O comando inicia/reutiliza um cluster exclusivo em `127.0.0.1:55432`, aplica
as migrations existentes somente ao banco `mission_control` e inicia o FastAPI
na porta 8000. Os arquivos do banco, senha e logs ficam ignorados pelo Git em
`.tools/mission-control/`. Não modifica `.env`, Docker ou serviços do sistema.
O diretório e a senha têm acesso restrito ao usuário; conexões TCP usam SCRAM.

Se a porta 8000 já estiver ocupada pela demonstração, basta abrir a URL.
Ctrl+C encerra o backend quando iniciado no terminal. O PostgreSQL isolado
permanece ativo para reutilização.

Para observar o banco M7 configurado no `.env`, quando esse banco estiver ativo:

```bash
./scripts/start-mission-control.sh
# Equivalente:
.venv/bin/python -m scripts.mission_control
```

Esse comando não cria nem migra o banco configurado no `.env`.
As credenciais Alpaca permanecem exclusivamente no backend.

## Funcionamento e limites

- A página usa somente `GET /health` e `GET /api/v1/broker/portfolio`, a cada
  aproximadamente 2 segundos, sem sobreposição e com timeout de 5 segundos.
- O processo de demonstração força `execution_mode=alpaca_paper`, usa um
  `ObservationWorker` que reaproveita reconciliação e snapshots do M7 e nunca
  chama `_process_pending_submits`. O `ObservationAdapter` bloqueia métodos
  diferentes de GET antes da chamada à Alpaca Paper. O backend de demonstração
  também rejeita métodos HTTP mutáveis, inclusive o pause já existente.
- O processo padrão `services.api.main:app` mantém seu comportamento M7.
  Para esta demonstração sem envio de ordens, use o comando acima.
- A reconciliação roda a cada 3 segundos mais o tempo das chamadas. Ela atualiza
  o armazenamento local; não cria, cancela ou substitui ordens na Alpaca.
  A ingestão de market data existente continua funcionando.
- `LIVE · TELEMETRIA` significa atualização da observação. A conta é sempre
  **ALPACA PAPER — DINHEIRO VIRTUAL**. Não é modo de execução LIVE.
- Estados: HEALTHY, DEGRADED, STALE (snapshot com mais de 15 segundos ou sem
  timestamp válido), BACKEND OFFLINE, SEM SNAPSHOT e MODO INCOMPATÍVEL.
  Dados anteriores ficam identificados como retidos em falhas; 404 e modo
  incompatível limpam os valores. Não há fallback para Local Paper.
- A timeline compara snapshots na memória da aba: reconciliação, equity,
  posições, status de ordens, fills e mudanças de saúde. Retém 40 eventos.
- Valores financeiros são exibidos a partir da API, sem somas ou reavaliação.
  O M7 atualmente persiste **zero no P&L agregado**, embora as posições tenham
  P&L do broker. A tela informa essa limitação. Buying power aparece somente
  se o contrato retorná-lo; o endpoint atual não o expõe.
- O banco isolado recebe saldo e posições reais da conta Paper. Orders/fills
  mostram apenas o que existe nesse banco; o histórico do banco M7 anterior
  não é importado nem sintetizado. Nenhuma ordem é criada para preencher a tela.
- Mercado fechado pode produzir snapshots novos com os mesmos preços e saldos.

## Verificação

```bash
EXECUTION_MODE=local_paper RUN_DB_TESTS=0 .venv/bin/pytest -q \
  tests/test_mission_control.py tests/test_health.py \
  tests/test_boundaries.py tests/test_alpaca_paper.py
.venv/bin/ruff check services/api/main.py services/api/mission_control.py \
  services/alpaca_paper/observation.py scripts/mission_control.py tests/test_mission_control.py
bash -n scripts/start-mission-control.sh
```

Os testes Python usam mocks; não acessam Alpaca nem banco real. Também foram
verificados no Firefox: estados de falha/recuperação com respostas simuladas,
timeline, valores retidos, ausência de controles de execução, texto externo
sem interpretação HTML, layout desktop e avanço dos snapshots reais Paper.
Selenium foi usado apenas em `/tmp` para essa verificação, sem dependência
adicionada ao aplicativo.

## PostgreSQL portátil em outra máquina Ubuntu compatível

A demonstração nesta estação usou pacotes Ubuntu 26.04 oficiais, extraídos sem
instalação de serviços. Para repetir em uma estação compatível, baixe
`postgresql-18`, `postgresql-client-18` e `libpq5` com `apt-get download` em um
diretório temporário e extraia cada `.deb` com `dpkg-deb -x` em
`.tools/mission-control/postgres`. Depois use `--isolated`.
Em outros sistemas, prefira um PostgreSQL já configurado e o comando sem essa opção.
