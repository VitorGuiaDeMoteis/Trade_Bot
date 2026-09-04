# M5 — núcleo seguro do Observer

Este documento registra o recorte original do núcleo. A etapa FAKE passou também
pela [validação física de API/Flutter](M5_FAKE_ACCEPTANCE.md); essa API somente lê
auditoria persistida, sem acionar os providers. Modelo real permanece pendente.

Recorte autorizado sobre `bc942b046d7f9f3961f4fe0352492d8849897613`, branch
`codex/m5-observer`. Somente análise por CLI e auditoria. M4 permanece aceito;
Flutter/Xiaomi M5 pendentes, M6 não iniciado. Nenhum fornecedor de IA integrado.

## Entrada e proveniência

`AIObserverSnapshot` 1.0 é um DTO imutável, sem Settings ou objetos de domínio.
[JSON Schema de entrada](contracts/observer-input.schema.json). A projeção por
allowlist ocorre também nos objetos aninhados; não copia dicionários inteiros.

| Permitido | Regra |
| --- | --- |
| as_of_utc, provider, session_state | UTC; alpaca/simulator; estados enumerados |
| símbolos/timeframe | 1..4 símbolos; somente 1h |
| candles | últimos 32 fechados por símbolo; até 128; OHLCV válido |
| últimos sinais | um por símbolo, tipo histórico e versão v1-deterministic |
| últimas decisões de risco | uma por símbolo, decisão e horário persistidos |
| paper opcional | as_of, paused, cash, equity, total_pnl, posições e preço médio |
| backtest aceito opcional | result_hash e resumo de métricas já calculadas |

Candles ordenados por `(open_time, symbol)`, sem duplicatas. Símbolos e decisões
ordenados. Datas, fechamento e geração de sinal/risco não podem ultrapassar as_of.
Última decisão de risco é consultada independentemente do último sinal: um sinal
recente sem decisão não apaga a decisão anterior conhecida. Não atribuir versão
histórica de risco que o banco não armazena. Versões Strategy desconhecidas falham.

A coleta é PostgreSQL **REPEATABLE READ / READ ONLY**. `session_state` é declarado
pelo operador para esse snapshot; default offline, sem consulta de sessão externa.
Não tratá-lo como comprovação independente de conectividade atual. Paper é lido através da
reconciliação existente, sem executar ordens nem implementar outra contabilidade.
O estado atual é omitido se for posterior a as_of; não há reconstrução histórica
da carteira. Posições preservam todos os ativos, inclusive fora da seleção de
candles, dentro do limite de quatro. Dados antigos mantêm seu próprio horário.

Um relatório só entra pela seleção local explícita de arquivo e `--accepted-hash`.
A CLI valida o contrato/checksum M4 antes da projeção; o adapter `collect` recebe
apenas relatórios previamente validados por esse chamador confiável. Rejeita curva
terminando após as_of. Não escolhe automaticamente o arquivo mais recente nem
recalcula métricas. Hash prova conteúdo, não certifica autoria ou aceite humano.

JSON canônico: UTF-8, chaves ordenadas, separadores compactos, sem NaN. Dinheiro é
string Decimal; não há conversão monetária para float. `input_hash` é SHA-256 dos
bytes canônicos. Máximo **65.536 bytes**; arquivo de análise é lido com teto +1.
Um snapshot salvo congela os fatos; repetir a coleta após mudanças no banco pode
alterar o hash. as_of é referência histórica explícita, não indicação de tempo real.

**Proibidos:** credenciais Alpaca/DB, tokens, account/run/signal IDs, `.env`, caminhos,
URLs, capabilities, Settings, razões livres e configuração secreta. O adapter
confiável de conexão lê somente POSTGRES_*; nenhum objeto de conexão atravessa
a fronteira do provider. Campo extra na entrada direta é rejeitado; campo não
permitido na fonte bruta é removido pela projeção. Segredos plantados são testados.

## Saída e falha segura

[JSON Schema de saída](contracts/observer-output.schema.json), gerado do mesmo
modelo Pydantic usado para validação, com teste de sincronismo. `extra=forbid`
em todos os objetos. Apenas schema_version, regime, risk_flags e observations.

- Regime: TRENDING/RANGING/VOLATILE/UNCERTAIN, confidence finita 0..1, até 8 evidências.
- Risk flags: até 8, códigos DATA_STALE/DATA_QUALITY/VOLATILITY/CONCENTRATION/LOW_LIQUIDITY;
  severidade LOW/MEDIUM/HIGH.
- Até 12 observações; strings 1..240 caracteres; resposta até **16.384 bytes**.
- Um único documento UTF-8 JSON; chaves duplicadas, prefixos/sufixos e JSON truncado
  são rejeitados. Validação adicional rejeita controles Unicode, URLs/caminhos,
  marcadores de segredo e vocabulário BUY/SELL/order/comandos em texto.

As validações semânticas adicionais não são todas expressáveis no JSON Schema;
o consumidor deve usar `parse_output`, não somente o arquivo de schema. O filtro
de texto é defesa adicional, não um detector completo de prompt injection.
A segurança principal é **não existir consumidor financeiro dessa saída**.

`PROMPT_VERSION=observer-v1`: observador, sem autoridade, sem promessa de retorno,
sem inventar dados, apenas snapshot e JSON. Seu hash e versão ficam em cada análise.
O fake sempre retorna UNCERTAIN; não faz inferência de mercado nem otimização.

Default desligado. `--enabled` habilita apenas esta análise. Snapshot inválido,
ausente/excessivo, sem candles para algum símbolo, provider degraded/delayed/offline,
dados mais de 2h atrasados em relação a as_of, timeout inválido ou erro do modelo
produzem **DEGRADED / HOLD**. `market_closed` não ignora a janela de frescor.
Esse HOLD pertence exclusivamente à auditoria; nunca é Signal, RiskDecision ou ordem.

Modelo inexistente: MODEL_UNAVAILABLE. Imagem/daemon indisponível ou falha de
processo: MODEL_ERROR. Timeout: TIMEOUT. Contrato inválido: INVALID_OUTPUT.
Não persistir stdout bruto, stderr ou mensagens de exceção. Se o próprio banco
estiver indisponível, não é possível persistir: a CLI falha explicitamente, sem
simular sucesso e sem tocar finanças. Falha de coleta ocorre antes de iniciar
uma análise; arquivo inválido passado a `analyze` registra INVALID_SNAPSHOT.

## Isolamento

`ModelProvider` é uma interface, não um loader de plugins. Só o fake revisado
executa no host. A CLI aceita fake ou `IsolatedProvider`; nenhum shell/comando
arbitrário, SDK, Ollama ou autenticação OpenAI foi configurado.

O cliente Docker confiável roda com cwd temporário e ambiente reduzido a
SystemRoot/WINDIR quando presentes, DOCKER_CONFIG vazio temporário e DOCKER_HOST
fixo: named pipe local Docker Desktop Linux no Windows ou socket local no Linux.
Não herda contexto Docker, helpers, PATH, POSTGRES_*, ALPACA_* ou tokens.

O modelo roda em imagem local identificada por `sha256`, `--pull=never`, sem volumes,
sem socket Docker, rede `none`, rootfs read-only, usuário 65534, capabilities
removidas, no-new-privileges, 128 MiB, 1 CPU, 32 processos. `/tmp` é tmpfs de 4 MiB,
noexec/nosuid, cwd do modelo. stdin contém somente snapshot; stdout contém resposta.
stderr é consumido/descartado, teto 4 KiB. O prompt versionado fica dentro da imagem
revisada; trocar imagem exige verificar prompt/contrato e registra outro model_version.

`evaluate` aplica timeout obrigatório: default 2s, configurável `0 < t <= 30s`.
O adapter cancela processo/contêiner no erro; limpeza tem teto adicional de 3s.
Logo timeout do modelo não é promessa de latência total igual a t. Falha do daemon
na limpeza é erro e requer inspeção local; não prova remoção de um daemon inacessível.
O teste real não deixou contêiner residual. Uso direto de `generate` por código
confiável deve conservar o deadline de `evaluate`.

O Docker daemon, kernel, imagem e operador são confiáveis. Não é uma VM dedicada
contra escape de kernel, nem se permite código de modelo arbitrário no host.
Suporte a modelo real está preparado pelo protocolo, **não integrado/validado**.
[Threat model e limitações](M5_THREAT_MODEL.md).

## Persistência

Migração `0009_m5_observer` cria somente `observer_analysis_runs`, sem FK/trigger
financeiro. Guarda analysis_id, created_at, as_of_utc, provider/model/versão,
prompt_version/hash, schema_version, request_hash, input_hash/output_hash,
status/fallback/error_code/latency_ms, sanitized_input e validated_output.
JSON ausente é SQL NULL. Constraints impedem OK sem input/output e DEGRADED sem HOLD.

UUID fornecido pelo operador é a chave idempotente. Advisory lock transacional
por UUID + PK serializam concorrência; o binding inclui input, provider/model,
prompt, enabled e timeout. Mesmo UUID/config retorna o registro existente sem
chamar modelo. UUID reutilizado com configuração diferente é conflito explícito.
Hashes/contratos do cache são validados; corrupção falha fechada.

INSERT é único e atômico; falha na persistência não deixa registro parcial. A
inferência ocorre antes do commit: crash antes dele pode repetir a inferência
no retry, mas não duplica uma análise já persistida. UUID diferente cria uma nova
análise, mesmo input. Espera pelo lock usa statement_timeout do banco (3s); uma
espera longa pode falhar e deve ser repetida com o **mesmo UUID**. Não há retry
automático ou promessa de exatamente uma inferência antes de commit.
Não há UPDATE/DELETE na aplicação Observer. O operador/role local do banco ainda
pode alterar tabelas: não é armazenamento inviolável nem isolamento por role SQL.

## Executar no PowerShell

Na raiz, com PostgreSQL local já configurado (sem solicitar chaves novas):

```powershell
uv sync --locked
docker compose up -d --wait postgres
uv run alembic upgrade head
uv run python -m scripts.observer --help

# Exemplo histórico: ajuste as_of ao conjunto local, sem inventar dados atuais.
uv run python -m scripts.observer snapshot `
  --as-of 2026-09-03T21:00:00+00:00 --provider alpaca `
  --symbols SPY AAPL TSLA --session-state market_closed `
  --output .artifacts/observer-snapshot.json

$analysisId = [guid]::NewGuid().ToString()
uv run python -m scripts.observer analyze .artifacts/observer-snapshot.json `
  --analysis-id $analysisId --enabled
# Repetir exatamente esse comando/UUID não duplica o registro.

# Fake em contêiner, sem credenciais ou downloads durante a análise:
docker build -t trading-bot-observer-fake:1 infrastructure/observer
$observerImage = docker image inspect trading-bot-observer-fake:1 --format '{{.Id}}'
uv run python -m scripts.observer analyze .artifacts/observer-snapshot.json `
  --analysis-id ([guid]::NewGuid().ToString()) --enabled --image $observerImage --timeout 10
```

Build pode baixar somente a imagem base pública; o contexto contém worker fake e
prompt, não repositório/.env. `--image` aceita ID imutável; nunca tag mutável.
Para incluir backtest acrescente `--backtest CAMINHO_LOCAL --accepted-hash HASH`
ao snapshot, somente após aceite explícito. Nenhum caminho é enviado ao modelo.
Retirar `--enabled` produz auditoria DISABLED/HOLD; não muda paper, risco ou pausa.

Não é necessário iniciar Uvicorn, Flutter, streaming ou API para usar o Observer.
O runtime existente inicia Alpaca quando `MARKET_DATA_PROVIDER=alpaca`, mesmo com
SIMULATOR_ENABLED=false; esse flag desliga somente o simulador. Não iniciar API
para um teste offline. Quando usada, manter API em 127.0.0.1, sem proxy/LAN.

Gates: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
`docker compose --profile test up -d --wait postgres_test`,
`$env:RUN_DB_TESTS='1'; uv run pytest -q`, `uv run alembic check`.
Banco de teste dedicado 127.0.0.1:5433; nunca rodar fixtures no banco de uso.
[Resultados finais](STATUS.md) e [evidência de isolamento](evidence/m5-isolation.json).
