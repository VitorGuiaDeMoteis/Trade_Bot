# M5 modelo real — diagnóstico e proposta OCI

2026-09-04. Base confirmada por `git pull --ff-only origin codex/m5-observer`
e `git ls-remote`: `094b588105ea6b34138dcf10c7df54b70efd2a57`.

**M5 real model: PENDING. M5 Acceptance: PENDING.** O aceite FAKE permanece válido.
Foi aplicada a alternativa expressa na seção 3 do pedido: diante de conflito
material de isolamento, documentar, propor OCI compatível e retornar pendente.
Não houve implementação de adapter, inferência, download de pesos, modelo cloud,
chamada Alpaca, mudança financeira, merge ou início do M6.

## Inventário observado

- Ollama instalado no Windows. A tentativa de `ollama list` iniciou o launcher,
  que anunciou versão 0.32.14, mas terminou com `timed out waiting for server to start`.
  Esse número é o informado pelo launcher, não uma versão validada de servidor ativo.
- Após a tentativa não havia processo Ollama nem listener na porta 11434.
- Um único manifesto no armazenamento local padrão: **deepseek-r1:8b**.
  O config local declara família qwen3, 8.2B, GGUF Q4_K_M. São metadados do arquivo,
  não certificação de autoria, especialização financeira ou capacidade de inferência.
- Pesos: 5.225.373.760 bytes. SHA-256 calculado e igual ao declarado:
  `e6a7edc1a4d7d9b2de136a221a57336b76316cfe53a252aeba814496c5ae439d`.
- Manifesto SHA-256:
  `6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`.
  Todos os cinco blobs referenciados existem e passaram tamanho/hash.
- `docker images` não mostrou runtime real de inferência. A imagem Observer
  disponível é somente `trading-bot-observer-fake:1`.
- Modelo candidato para a próxima etapa: o deepseek já presente. Nenhum modelo
  foi escolhido como provider operacional; `provider/model_version` de uma análise
  real ainda não existem. A integridade dos arquivos não prova execução correta.

## Conflito material de isolamento

O [threat model aprovado](M5_THREAT_MODEL.md) trata o processo do modelo como uma
fronteira isolada: sem rede, mounts do host, ambiente herdado, socket Docker ou
credenciais; usuário sem privilégios e limites de recursos. Isso está implementado
em `services/observer/isolated.py`, não apenas descrito no prompt.

Um adapter host HTTP com destino fixo `127.0.0.1:11434`, sem proxy/redirect/tools,
limita o **cliente**, mas não coloca o servidor Ollama nativo dentro dessa fronteira.
Não há isolamento de filesystem/rede do processo nativo demonstrado nesta máquina.
Não se afirma que os pesos executaram comandos ou acessaram segredos: nenhuma
inferência foi feita. A incompatibilidade é de garantias de implantação.

A documentação oficial distingue bind local, ambiente herdado no Windows e opção
de desligar recursos cloud. Desligar cloud não equivale a sandbox de SO.
[Ollama FAQ](https://docs.ollama.com/faq). Inferência: usar o servidor nativo sem
isolamento adicional reduziria as garantias OCI atuais. Não basta corrigir seu startup.

## Proposta concreta para execução OCI real

1. Preparar imagem Linux revisada com runtime de inferência fixado por digest,
   usando os pesos locais acima, sem `ollama pull`. O runtime Linux ainda precisa
   ser disponibilizado; não existe imagem real local pronta nesta inspeção.
2. Contexto de build mínimo, fora da árvore de segredos: somente runtime/pesos
   verificados, wrapper, schema e prompt `observer-v1` exato. Nunca copiar a pasta
   `.ollama` inteira, chaves de autenticação, `.env` ou o repositório. Incorporar
   pesos à imagem permite executar sem montar diretórios do host.
3. Manter protocolo host `generate(snapshot: bytes, prompt: str) -> bytes` e
   stdin/stdout do `IsolatedProvider`. Se usar Ollama dentro da imagem, wrapper
   confiável fala somente com `127.0.0.1:11434` **interno**; nenhuma porta publicada,
   rede `none`, cloud desabilitada, sem proxy, redirects, tools ou endpoints de pull.
4. Manter rootfs read-only, UID não privilegiado, capabilities removidas,
   no-new-privileges, sem Docker socket, sem mounts/env do host e tmpfs limitado.
   Autorizar apenas o modelo incorporado; conferir digest antes/depois e registrar
   identidade exata do modelo e da imagem, preservando a allowlist pública da API.
5. Definir perfil explícito de recursos para modelo real: os atuais 128 MiB,
   1 CPU, tmpfs 4 MiB e deadline máximo de 30 s são o perfil FAKE, não uma capacidade
   comprovada para os pesos de 5,23 GB. Medir memória/contexto/latência e revisar
   limites sem remover tetos ou desligar timeout. Não relaxar automaticamente o core.
6. Usar JSON estruturado do runtime e manter parser/schema/filtros existentes como
   autoridade. Sem reparar JSON. Rejeitar excessos de bytes, saída livre e campos
   executáveis; toda falha fica DEGRADED/HOLD, sem consumidor financeiro.
7. Executar todos os testes adversariais solicitados, prova de isolamento OCI real,
   análise e timeout persistidos, comparação financeira e fluxo físico Xiaomi.
   Até isso ocorrer, nenhum aceite do modelo real.

Essa é uma proposta, não uma implantação já validada. A documentação Docker do
Ollama oferece runtime em contêiner, mas seus exemplos com volumes/portas não são
o perfil seguro acima: [Ollama Docker](https://docs.ollama.com/docker).

## Gates executados novamente

Na raiz: `uv run ruff format --check .` (121 arquivos encontrados),
`uv run ruff check .`, `uv run mypy` (68 arquivos): OK.
`docker compose --profile test up -d --wait postgres_test`: healthy.
`$env:RUN_DB_TESTS='1'; uv run pytest -q`: **282 passaram em 35,18 s**,
212 sem PostgreSQL e 70 PostgreSQL. Contagem confirmada com
`uv run pytest --collect-only -q -m integration`.
`uv run alembic check`: nenhuma operação nova.
Aviso preexistente Starlette/AnyIO, sem falhas ou testes removidos.

Após `. ./scripts/use-android.ps1`, em `apps/mobile_app`: `flutter analyze` OK,
`flutter test` **83 passaram**, `flutter build apk --debug
--dart-define=API_BASE_URL=http://127.0.0.1:8000` compilou realmente.
Não reinstalado: não houve alteração de aplicativo nem análise real a apresentar.
`adb devices -l` confirmou Xiaomi 1791a20e; `adb reverse --list` confirmou túnel 8000.
Backend existente continua exclusivamente 127.0.0.1:8000.

Gates provam que a base existente continua passando, **não** validam adapter real
inexistente. Não foram adicionados testes redundantes. Testes adversariais do
provider real, fallback real, análise real e Xiaomi real permanecem não executados.
Capturas FAKE não são renomeadas como REAL. Não existem novos artefatos de análise
ou screenshots reais de modelo; diagnóstico em `evidence/m5-real-preflight.json`.

## Não interferência

SELECTs de comparação feitos em REPEATABLE READ / READ ONLY no banco de uso.
Hashes/counts antes/depois incluem todas as nove tabelas Paper, signals,
risk_decisions e observer_analysis_runs. Relatórios M4 comparados por hash de bytes.
Os gates PostgreSQL usam apenas o banco dedicado em 5433.
Essa comparação prova a preservação durante o diagnóstico; não simula uma prova
de não interferência de inferência real, que não aconteceu.

Resultado: todas as tabelas e relatórios idênticos. Signals 2.193, RiskDecisions
2.193, 1 ordem, 1 fill, LONG TSLA 3, cash 9084.3458912448, paused=true. Auditoria
Observer permaneceu com oito registros FAKE; nenhuma análise real foi simulada.
[Counts e hashes antes/depois](evidence/m5-real-preflight.json).
