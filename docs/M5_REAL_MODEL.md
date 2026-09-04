# M5 — modelo local em OCI

Integração autorizada sobre `c0efa10b22abda755c1dd52aefdde8c8de7483d1`,
branch `codex/m5-observer`. Um único modelo: deepseek-r1:8b já instalado.
Não é modelo especializado em finanças; o config local identifica qwen3/8.2B/Q4_K_M.
Nenhuma otimização de estratégia ou previsão de rentabilidade.

## Imagem e contexto

Base oficial única baixada: `ollama/ollama@sha256:57a73f11f75b32b97b59b003f351445c9c2a8af4b9d586ecdc928dee6150ef26`.
Inventário pré-pull: 102.912.348.160 bytes livres, 3.705.521.862 bytes estimados de
download. Nenhum peso baixado. Python/musl do wrapper foi reutilizado da imagem
FAKE local `sha256:8c3c56c0b12bf22016d4383696838395d4694bb7fa58e0714c4a71a7413ed80a`;
nenhuma segunda imagem de runtime, pip ou apt foram baixados.

`scripts/build_observer_real.py` verifica os cinco blobs antes e após copiá-los.
Contexto temporário contém somente manifesto/blobs exatos, Dockerfile, wrapper,
prompt observer-v1 e schema de saída. Não contém repo, .git, .env, credenciais,
config Ollama do usuário, logs, DB ou socket. Build usa `--pull=false --network=none`.
Runtime verifica novamente manifesto e todos os blobs antes de iniciar Ollama.

Pesos (5.225.373.760 bytes):
`sha256:e6a7edc1a4d7d9b2de136a221a57336b76316cfe53a252aeba814496c5ae439d`.
Manifesto:
`6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`.
Somente o nome/digest incorporados são aceitos. A tag de build é conveniência;
a CLI recebe ID imutável e valida labels antes da execução.

## Perfil REAL separado

| Recurso | Limite |
| --- | --- |
| RAM / RAM+swap | 7 GiB / 7 GiB (sem swap adicional) |
| CPU | 6 |
| GPU | opcional explícita device=0; RTX 4060 Ti de 8 GiB verificada, sem mudança no host |
| PIDs | 128 |
| tmpfs /tmp | 64 MiB, noexec/nosuid |
| Contexto | GPU v2: 32.768 tokens; CPU: 16.384 |
| Tokens gerados | GPU v2: 8.192; CPU: 1.024 |
| Entrada / saída | 65.536 / 16.384 bytes |
| Envelope HTTP interno | 131.072 bytes |
| Deadline do perfil REAL | máximo 900 s, inclui preflight e geração; limpeza até +3 s |
| Timeout HTTP interno | 880 s; protegido pelo deadline externo |

FAKE permanece 128 MiB, 1 CPU, 32 PIDs, tmpfs 4 MiB e timeout máximo 30 s.
A extensão exige `RealIsolatedProvider`; identidade textual não concede outro teto.
CLI não inicia automaticamente: exige `--enabled --real-image ... --timeout 900`.
GPU exige também `--real-gpu` e imagem construída com `--gpu`; labels e binding
impedem trocar silenciosamente os perfis. CPU continua sem acesso à GPU.
GPU não recebe limite artificial de VRAM: o dispositivo 0 físico tem 8.188 MiB;
um único modelo/processamento, contexto e geração têm os limites acima.
Na prova GPU v2 foram medidos 6.040.776.704 bytes de RAM e 6.330.242.825 bytes de
modelo/cache em VRAM. Não foi instalado driver nem alterada proteção do host.

Imagem roda sem rede, volumes do host ou portas publicadas, rootfs read-only,
UID/GID 65534, cap-drop ALL, no-new-privileges. Docker cliente recebe ambiente
reduzido e daemon local fixo. O modelo nunca recebe conexão SQL/Settings/segredos.
O wrapper inicia somente o binário fixo Ollama; nunca interpreta saída como comando.

## Transporte, identidade e saída

Servidor escuta apenas `127.0.0.1:11434` dentro do namespace sem rede. HTTP stdlib
não herda proxy nem segue redirect; apenas GET /api/tags e POST /api/chat internos.
Sem tools/functions, pull, endpoint configurável ou acesso de browser do modelo.
Ambiente do servidor é uma allowlist; OLLAMA_NO_CLOUD=1 e um modelo carregado por vez.

Prompt observer-v1 exato e snapshot são as únicas mensagens. Schema vai no campo
format, stream=false, temperature=0, seed=0. CPU usa think=false; GPU usa think=true
para que o runtime separe raciocínio do documento final. O template local é o do
manifesto verificado. O campo separado de thinking é descartado; conteúdo com
prefixo/sufixo, markdown, `<think>`, duplicatas, NaN ou truncamento é rejeitado.
Não existe reparo de JSON. Contadores e done_reason do runtime devem indicar
conclusão com margem de contexto; truncamento próximo do limite falha fechado.
Saída passa novamente pelo `parse_output` do host, schema e filtros semânticos.
[API Ollama](https://docs.ollama.com/api/generate) e
[saída estruturada](https://docs.ollama.com/capabilities/structured-outputs).

Identidade vem do adapter confiável: provider=oci-local, model=deepseek-r1:8b,
model_version=SHA dos pesos, image_digest separado. Migração 0010 adiciona apenas
essa coluna nullable à auditoria Observer; registros FAKE anteriores permanecem válidos.
Binding idempotente REAL inclui a imagem; mesma UUID com outra imagem é conflito.
Binding FAKE anterior não muda. API continua GET, sem importar/iniciar provider;
revalida allowlist de identidade/hash/saída. Flutter apenas apresenta a auditoria.

## Executar

O pull do digest acima é uma preparação explícita autorizada; nunca é feito pelo
Observer. Não executar ollama pull. Depois do runtime disponível, na raiz:

```powershell
uv run python -m scripts.build_observer_real --models "$env:USERPROFILE/.ollama/models" --gpu
uv run alembic upgrade head
$observerImage = docker image inspect trading-bot-observer-real:1 --format '{{.Id}}'
uv run python -m scripts.observer analyze .artifacts/m5-snapshot.json `
  --analysis-id ([guid]::NewGuid().ToString()) --enabled --real-image $observerImage --real-gpu --timeout 900
```

Para a UI, usar o backend com MARKET_DATA_PROVIDER=simulator e SIMULATOR_ENABLED=false,
apenas 127.0.0.1:8000, Xiaomi1791a20e por adb reverse. Nenhuma coleta Alpaca ocorre
durante a inferência. Falhas não mudam pause, Signal, Risk, Paper ou Backtest.

## Limitações

CPU é lenta para snapshots grandes. Timeout/falha produz auditoria DEGRADED/HOLD;
HOLD não é Signal e não altera Strategy/Risk. Não há garantia de acerto financeiro,
de determinismo entre versões/hardware ou de veracidade absoluta das observações.
Mesmo seed/modelo são identificáveis na auditoria; não há ajuste para lucro.
Host, daemon, imagem revisada e operador permanecem confiáveis. Hash não é assinatura
contra operador privilegiado; nenhum acesso financeiro foi concedido ao modelo.

## Problemas reproduzidos

Um timeout interno era classificado genericamente como MODEL_ERROR. O wrapper
agora usa exit 124, mapeado exclusivamente pelo provider REAL para TIMEOUT/HOLD.
Regressões cobrem esse caminho; o provider FAKE e seu teto permanecem intactos.
O perfil GPU inicial terminou por limite de geração: 13.358 tokens de entrada,
2.048 tokens gerados e conteúdo final vazio. Apenas contagens foram examinadas;
nenhum raciocínio foi salvo. GPU v2 reserva mais contexto e tokens e exige
done_reason=stop; truncamentos continuam DEGRADED, nunca são reparados.
