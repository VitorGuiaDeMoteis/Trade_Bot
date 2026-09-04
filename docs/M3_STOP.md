# M3 — STOP local no Flutter

Correção de aceite em 2026-09-04, sobre
`ffd94fb33c408d7ea1f192c2e189b999f9a4b654`, branch `codex/m3-paper`.

## Contrato e decisão de segurança

O app pode **PARAR**, nunca retomar. Uma ação que apenas reduz autoridade não
precisa carregar o segredo de comandos que permitem execução. O contrato anterior
de Bearer para STOP foi substituído explicitamente por uma permissão local de STOP,
sem senha, token, segredo de build ou segredo permanente no APK.

```http
POST /api/v1/paper/pause HTTP/1.1
Host: 127.0.0.1:8000
X-Paper-Control: stop
Content-Length: 0
```

Resposta após commit: `200 {"paused": true}`, `Cache-Control: no-store`.
O cabeçalho é um marcador público de intenção, **não uma credencial**.
Não há campo `paused=false`, token no body, nem `/resume`, `/reset`, BUY/SELL/order.
`PAPER_CONTROL_TOKEN` foi removido da configuração; não é necessário criá-lo.

Todas as condições abaixo são exigidas:

- Peer TCP loopback, IPv4 ou IPv6; Host exatamente 127.0.0.1, localhost ou ::1.
- Nenhum Origin, mesmo vazio ou `null`; nenhum Referer ou `Sec-Fetch-*`.
- Nenhum `Forwarded` ou `X-Forwarded-*`; não há suporte a reverse proxy.
- Cabeçalho `X-Paper-Control: stop` e corpo vazio, inclusive em transferência chunked.
- Somente POST. GET/OPTIONS não executam; CORS não é habilitado.

Peer/Host/cabeçalhos indevidos retornam 403; corpo não vazio retorna 422; banco ou
integridade indisponível retorna 503. O corpo é rejeitado no primeiro chunk, sem
acumular uma carga arbitrária. IP remoto não é autorizado por conhecer o cabeçalho.
Host local também reduz o risco de DNS rebinding. JavaScript de navegador não pode
enviar o cabeçalho customizado sem preflight e os metadados de navegador são recusados.

Threat model: backend ligado somente a `127.0.0.1`, PostgreSQL em loopback, Xiaomi
confiável via `adb reverse`, servidor sem proxy e sem confiança em proxy headers.
Outro processo local ou aplicativo no tablet com acesso ao túnel também pode
**parar** a simulação. Esse risco residual de indisponibilidade é aceito: não pode
reativá-la, alterar cash/posições ou criar ordens. Isso não autentica o aplicativo
e não serve para implantação pública, LAN, túnel remoto ou futuros comandos de
execução. Não reutilizar essa política para aumentar autoridade.

O lock/transação da pausa permanece o mesmo: espera o lote em andamento terminar
e confirma apenas após persistir `paused=true`. Nenhum lote posterior pode executar.
Repetir STOP é idempotente e não gera outro evento nem altera a carteira.

## Flutter

A carteira usa `API_BASE_URL`, como o restante do app, em vez do endereço de
emulador embutido. O controller envia somente POST vazio com o marcador público.
Há timeout de cinco segundos, serialização de requisições e descarte seguro do
controller ao sair da página. Nenhum saldo oficial é calculado no cliente.

Texto do botão: **PAUSAR SIMULAÇÃO**. Depois da confirmação:

```text
SIMULAÇÃO PAUSADA
Novas ordens simuladas bloqueadas.
Para retomar, use a CLI local.
```

No contrato financeiro, `status=RUNNING` descreve o progresso do replay; o controle
fica em `paused=true`. A UI apresenta PAUSED enquanto esse controle estiver ativo.

Não há botão de retomada. Cash e posições continuam visíveis durante a requisição.
Erro/timeout não é tratado como sucesso. Se o STOP confirmou mas a consulta seguinte
falhou, a tela mantém a confirmação e identifica os valores como última consulta.
Uma atualização posterior reflete eventual retomada feita explicitamente pela CLI.

## Executar

```powershell
# Raiz do projeto; manter o backend em loopback, sem proxy
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --log-config infrastructure/docker/logging.json --ws websockets-sansio
```

```powershell
# Outro terminal
. ./scripts/use-android.ps1
adb -s 1791a20e reverse tcp:8000 tcp:8000
cd apps/mobile_app
flutter run -d 1791a20e --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Retomada exige operador na CLI local, na raiz:

```powershell
uv run python -m scripts.paper resume
uv run python -m scripts.paper replay
```

Não executar esses comandos para encerrar a demo: o estado final desta validação
foi deixado **pausado**. Não foi criado mecanismo de retomada remota.

## Testes e prova física

| Verificação | Resultado |
| --- | --- |
| Ruff format/check e mypy | OK, 50 módulos tipados |
| `RUN_DB_TESTS=1` + `uv run pytest -q` | 178 passaram: 132 unitários + 46 PostgreSQL |
| Novos casos Python | 16 cenários de peer/Host/Origin/browser/proxy/corpo/método; teste PostgreSQL existente adaptado ao STOP local e idempotência de todas as tabelas |
| `flutter analyze` | No issues found |
| `flutter test` | 71 passaram; 11 novos casos de contrato, falhas, descarte, botão real em widget, preservação de valores e ausência de controle antigo no código |
| Widget layouts | 360x800, 800x360, 800x1280, 1280x800; botão com pelo menos 48 dp; sem overflow |
| `flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000` | APK normal compilado |
| `adb devices -l` + `flutter devices` | Xiaomi 23073RPBFG, 1791a20e, Android 15/API35, arm64 |
| `adb install -r …app-debug.apk` + `am start` | Success; app em primeiro plano, PID 966 |
| Toque no botão do Xiaomi | RUNNING → PAUSED; confirmação vista na UI e no REST |
| CLI replay após pausa | Exit 1, `paper_paused`; nenhuma tabela paper alterada |
| STOP repetido na API real | 200; todas as tabelas paper inalteradas |
| Origin `null`, ausência do marcador, body com false na API real | 403, 403, 422, sem efeito |
| `/api/v1/paper/resume` | 404 |
| Logcat filtrado pelo PID do app | Zero crash, exceção Flutter ou overflow encontrado |

O banco de desenvolvimento estava sem run. Foi feito backup local ignorado
`.artifacts/m3-stop-before.sql` (2.841.291 bytes), preservando dados de mercado.
O replay foi executado explicitamente até o checkpoint 2 e deixado pausado após
o toque físico. Run: `87cde257-5ae7-450b-bc80-c90dd35938ab`, 600 candles congelados.

| Campo | Antes e depois do STOP |
| --- | --- |
| Cash | 9084.3458912448 USD |
| Equity | 10002.9158912448 USD |
| Posição | LONG TSLA, 3 ações |
| Ordens / fills | 1 / 1 |
| Checkpoint | 2 |

Comparação incluiu IDs, listas completas de ordens/fills/posições, valores e hash
de todas as linhas das tabelas paper. Não foi retomada a simulação após o teste.
Nenhuma configuração global do Android foi alterada; prova física em paisagem.
Capturas inspecionadas:

- [RUNNING com botão](evidence/m3-stop-xiaomi-running.png)
- [PAUSED com carteira preservada](evidence/m3-stop-xiaomi-paused.png)
- [TSLA preservada após STOP](evidence/m3-stop-xiaomi-positions.png)

Busca no código Flutter não encontrou credencial antiga, toggle ou RESUME.
Busca nos caminhos executáveis pelos quatro padrões proibidos de Trading API:
zero ocorrências. Alpaca continua somente Market Data. Nenhum segredo foi lido
para o app, adicionado ao APK, impresso ou versionado. Sem merge ou M4.

Avisos não bloqueantes: depreciação Starlette/AnyIO e versão XML do SDK Android.
Todos os gates e o build passaram. **M3 acceptance: APPROVED** para a correção
do último blocker de pausa, junto à auditoria financeira anterior.
