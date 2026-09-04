# Threat model — núcleo M5

Escopo original do núcleo preservado abaixo. A extensão HTTP/Flutter FAKE tem
aceite e fronteiras em [M5_FAKE_ACCEPTANCE](M5_FAKE_ACCEPTANCE.md#api-e-segurança-funcional):
somente GET de auditoria, com schema/hash/metadados revalidados e sem ModelProvider.
Não acrescenta autoridade financeira ou exposição LAN. Modelo real não integrado.

## 1. Overview

Escopo: Observer local por CLI, autorizado pelo usuário sobre M4 aceito. Não é
uma auditoria de todo o produto. Revisão de arquitetura feita sequencialmente,
sem revisor independente. Hipóteses abaixo não são vulnerabilidades confirmadas.

| Componente | Papel e evidência |
| --- | --- |
| CLI confiável | Seleciona snapshot, UUID, provider e aceite M4: `scripts/observer.py:22` |
| Coletor confiável | SELECT consistente e reconciliação somente leitura: `services/api/observer_source.py:38` |
| Contratos/core | Projeção, limites, hash, validação/fallback: `services/observer/snapshot.py:18`, `services/observer/engine.py:15` |
| Processo modelo | Apenas stdin/stdout em OCI: `services/observer/isolated.py:24` |
| Auditoria confiável | Um INSERT transacional, sem tabelas financeiras: `services/api/observer_store.py:17` |

| Deployment or workflow | Resource or capability | Configuration and precedence | Safe effective value or location | Readers, writers, or recipients | Enforcing control | Evidence or unknowns |
| --- | --- | --- | --- | --- | --- | --- |
| CLI host | Conexão PostgreSQL | POSTGRES_*: argumentos de Settings > ambiente > .env > defaults | defaults 127.0.0.1:5432/trading_bot_dev; testes explicitamente 5433 | Adapter confiável; nunca modelo | Settings específico DB, projeção e READ ONLY na coleta | `services/api/observer_database.py:8`, `services/api/observer_source.py:39` |
| CLI snapshot | JSON de saída local | --output explícito | arquivo escolhido pelo operador; exemplos .artifacts/ | Host escreve; operador pode ler | Publicação atômica existente; projeção remove paths/config | `scripts/observer.py:64` |
| Backtest opcional | Arquivo de relatório | --backtest + --accepted-hash | arquivo local validado; só resumo/hash no DTO | CLI lê, modelo recebe resumo | Validação M4 + hash selecionado; sem busca automática | `scripts/observer.py:50`, `services/api/observer_source.py:148` |
| Fake in-process | Código Python | provider default da CLI | FakeProvider revisado | Host confiável | Não aceita import/código fornecido pelo modelo | `scripts/observer.py:69`, `services/observer/provider.py:22` |
| Docker cliente host | Daemon e env | executável absoluto via busca local; contexto não herdado | Windows named pipe DockerDesktopLinuxEngine; Linux /var/run/docker.sock; DOCKER_CONFIG temp | Apenas cliente Docker confiável | Env allowlist e cwd temporário; sem shell | `services/observer/isolated.py:50` |
| OCI modelo | FS/rede/processos | --image SHA local; flags não substituíveis pela resposta | /tmp tmpfs 4MiB; root read-only; rede none; 128MiB/1CPU/32PIDs | Modelo não recebe mount, socket, env do host | UID65534, cap-drop ALL, no-new-privileges, limites OCI | `services/observer/isolated.py:27`, `infrastructure/observer/Dockerfile:1` |
| Resposta modelo | stdout/stderr | constantes e timeout CLI | 16KiB stdout; 4KiB stderr descartado; 2s default, máximo30s, limpeza+3s | Core confiável valida | JSON estrito, teto e cancelamento | `services/observer/isolated.py:72`, `services/observer/engine.py:54` |
| Auditoria | observer_analysis_runs | UUID + binding configurado pelo host | PostgreSQL, migração0009; sem raw output | Adapter escreve, operador administra | PK, lock, transaction, hashes, constraints | `services/api/observer_store.py:26`, `services/api/models.py:260` |

## 2. Threat Model, Trust Boundaries, and Assumptions

Ativos: credenciais locais, integridade de saldo/posições/ordens/risco/backtests,
relação entre snapshot e análise, disponibilidade limitada do host. IA não tem
autoridade sobre o plano financeiro. Histórico BUY/SELL é dado de entrada, não
capability. HOLD de fallback fica exclusivamente na tabela de análises.

Atores: operador local confiável pode escolher arquivo/imagem, possui Docker e DB;
adversário do modelo pode controlar stdout/stderr e tentativas de consumo de
recursos, mas não o cliente Docker ou host. Conteúdo de dados é não confiável até
passar DTO/cronologia. Não há endpoint Observer remoto, multiusuário ou token M5.

Fronteiras independentes: banco → projeção READ ONLY → DTO imutável; DTO → stdin
do contêiner; stdout → validação estrita → INSERT de auditoria. Nenhuma aresta de
retorno ao executor/risco/controle. Core não importa SQLAlchemy/config/engines;
adapter host tem DB privilegiado, portanto não se alega uma role SQL isolada.
`services/api/observer_source.py:130` reutiliza reconciliação existente, sem
invocar execução nem criar contabilidade paralela.

Premissas: SO/kernel/daemon e imagem revisada são confiáveis; isolamento OCI não
resolve escape de kernel ou operador comprometido. Modelo real/vendor ainda não
integrado. Imagem revisada deve incorporar exatamente o prompt versionado; hash
de imagem registra a escolha, não verifica sozinho essa correspondência.
O teste de prompt cobre a imagem fake fornecida. Hash não é assinatura contra
um escritor privilegiado no DB/relatório. Não se afirma ausência de segredos em
pesos arbitrários de terceiros; neste recorte nenhuma inferência real é usada.

Contexto autorizado: backend loopback/Xiaomi por adb reverse mantido. A CLI M5
não inicia API nem coleta. Discrepância histórica identificada: SIMULATOR_ENABLED
false não desliga o provider Alpaca (`services/api/simulator_runtime.py:42`).
Não modificar esse runtime fora do recorte; para demo offline não iniciar API.

## 3. Attack Surface, Mitigations, and Attacker Stories

| Priority | Scenario and capability gain | Prerequisites | Impact | Existing controls | Mitigation | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Alta | Modelo tenta obter DSN/key e contactar executor | Modelo controla conteúdo/processo, sem host | Exfiltração ou escrita financeira se boundary falhasse | Nenhum segredo no DTO; rede none; nenhum volume/socket; sem canal executor | Preservar essas restrições em qualquer provider futuro | `services/observer/snapshot.py:18`, `services/observer/isolated.py:24`; teste real evidence/m5-isolation.json |
| Alta | Modelo devolve BUY/SELL/order ou instrução de pause | Controle de stdout | Autoridade financeira só existiria com novo consumidor indevido | Schema fechado + filtros; nenhuma função financeira no core | Não conectar relatórios a comandos; teste AST mantém fronteira | `packages/contracts/observer.py:174`, `tests/test_observer.py:242` |
| Média | Saída gigante, travamento, fork ou flood de stderr | Processo modelo ativo | Negação de uma análise/recursos locais | Bytes, timeout, PID/mem/CPU caps, limpeza | Em daemon indisponível inspecionar contêiner exato localmente; não retomar trading por isso | `services/observer/isolated.py:72`, `services/observer/engine.py:58` |
| Média | Repetição concorrente altera auditoria ou duplica run | Mesmo UUID invocado por CLIs locais | Audit trail inconsistente | Lock + PK + binding, cache validado, INSERT atômico | Retry mesmo UUID; não gerar outro automaticamente | `services/api/observer_store.py:26` |
| Média | Snapshot usa fechamento/decisão futura | Fonte com histórico pós-as_of | Análise enganosa/look-ahead | Filtro SQL, último risco independente, validação UTC/cronologia | Manter as_of explícito e snapshot congelado | `services/api/observer_source.py:71`, `packages/contracts/observer.py:127` |
| Baixa | Prompt injection textual em resposta | Modelo tenta escrever instruções | Texto enganoso sem autoridade | Campos/listas limitados, filtros, sem execução/renderização M5 | UI futura deve apresentar como opinião, não controlar sistema | `packages/contracts/observer.py:181` |
| Condicional | Operador escolhe imagem/cliente Docker adulterado | Já controla host/configuração confiável | Pode possuir autoridade do host previamente | Sem plugin arbitrário; imagem local por hash; contexto de build mínimo | Revisar imagem e executável; host comprometido fora do modelo | `services/observer/isolated.py:16`, `infrastructure/observer/Dockerfile:1` |

Nenhuma hipótese acima é apresentada como exploração confirmada. Gates adversariais,
prova real do contêiner e comparação financeira estão em STATUS. A auditoria pode
falhar se DB indisponível; não há promessa de persistência em armazenamento inacessível.

## 4. Severity Calibration (Critical, High, Medium, Low)

- **Critical:** comando de modelo causando movimentação real exigiria Trading API
  e autoridade que não existem aqui; classificar este núcleo assim seria infundado.
- **High:** escape demonstrado do processo para ler segredos do host ou escrever
  finanças; stdout contendo uma palavra de ordem, bloqueado, não demonstra escape.
- **Medium:** quebra reproduzida de idempotência/auditoria ou DoS além dos limites;
  falha de uma análise persistida com HOLD e nenhuma alteração financeira é controle funcionando.
- **Low:** texto limitado enganoso sem capability, ou lacuna de documentação local.
  Operador que já pode editar DB/imagem não ganha privilégio novo simplesmente por
  fazê-lo. Evidência de impacto deve ser separada de suposição sobre exposição remota.
