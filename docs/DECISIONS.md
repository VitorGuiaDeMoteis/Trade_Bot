# Decisões M4 — núcleo (2026-09-04)

- Backtest como orquestrador offline dos domínios existentes; contabilidade continua
  exclusivamente em PaperExecutor/PaperBook, sizing em risco. Sem estratégia nova.
- PostgreSQL fornece snapshot READ ONLY/REPEATABLE READ; manifest e relatório JSON
  separados da carteira corrente. Sem tabela/migração nova nem retomada do paper.
- Ordenação temporal por OPEN/símbolo e fases OPEN → fills → CLOSE → sinais,
  mantendo as regras M3. Overlap entre grupos é erro; nenhum fechamento futuro no sizing.
- Reinício reexecuta o manifest inteiro. SHA-256, versões e UUID5 estabilizam saída;
  artefato publicado atomicamente. Alterar regras exige incrementar a versão.
- Operação = roundtrip encerrado. Win rate/médias/profit factor líquidos de fees;
  slippage já embutido nos preços. Sem liquidação final artificial. Drawdown por
  fechamento, capital inicial como pico inicial; métricas indefinidas usam null.
- Relatório marcado BACKTEST; pausa da carteira corrente preservada. Replay visual
  e dashboard excluídos por solicitação explícita; não declarar M4 visual concluído.

[Definições, justificativas, fórmulas e evidências](M4_CORE.md).

---

# Decisão M3 — STOP sem segredo permanente (2026-09-04)

Adotada permissão local monotônica: o aplicativo só pode reduzir autoridade por STOP.
Descartados token permanente no APK e retomada remota. Peer/Host loopback, cabeçalho
não secreto, corpo vazio e rejeição de navegador/proxy formam o limite local.
Outro processo local pode causar pausa, mas não iniciar operações. CLI é o único
caminho de retomada/reset. Nenhum mecanismo de credenciamento novo é necessário.

[Justificativa completa, contrato e testes](M3_STOP.md).

---

# Decisões — M0 e M1

Fonte oficial: README, PRODUCT, ARCHITECTURE, MILESTONES e IMPLEMENT. Nenhuma mudança de produto ou de stack.

| ID | Decisão | Motivo e limite |
| --- | --- | --- |
| D001 | Monorepo nesta pasta, documentos originais copiados do pacote fornecido | A pasta atual tinha somente `.git`; preservar especificação junto do código. |
| D002 | Flutter 3.44.7 / Dart 3.12.2 já instalados, Android como alvo principal | Não atualizar o SDK global. Web é um alvo Flutter auxiliar de inspeção; não substitui aceite no tablet. |
| D003 | Python 3.12 em `.venv`, dependências fixadas em `uv.lock` | Usar uma versão já instalada; não alterar o Python 3.14 global. |
| D004 | FastAPI em processo único e pacotes Python separados | `api`, `market_simulator`, `strategy_engine`, `risk_engine`, `paper_executor`, `contracts` e `domain` preservam fronteiras. Somente API tem comportamento no M0. |
| D005 | PostgreSQL 17 em Compose, SQLAlchemy 2 e psycopg 3, Alembic | Persistência e migrações com o banco especificado. Desenvolvimento e integração possuem bancos separados. |
| D006 | Migração baseline `0001_m0` sem entidades de negócio | Alembic mantém sua tabela de versão. Candles entram no M1; ordens e carteira em marcos posteriores. Não antecipar tabelas e regras. |
| D007 | `/health` como readiness, HTTP 200 ou 503 | Consulta real ao banco e revisão da migração. Banco inacessível ou schema pendente resultam em `degraded`; não esconder falha. Contrato `schema_version: 1.0`. |
| D008 | API e banco acessíveis somente em loopback | M0 não tem login nem endpoints de controle. Não expor na LAN/Internet. Autenticação deve preceder futuros comandos protegidos. |
| D009 | Tela inicial local, tema escuro e `SIMULADO` fixo | Estado vazio verdadeiro, sem métricas inventadas, sem botões de operação e sem conexão ao backend. Único botão abre informações reais da versão. |
| D010 | Estados de rede apenas quando existir consumo de rede | No M0 a tela é local. Loading, offline, erro e conexão do app serão tratados na fatia visual M1; backend já informa degradação. |
| D011 | Testes de viewport, texto 200%, contraste e toque >=48 dp | Complementam, mas não substituem, execução física em retrato e paisagem. Teste de integração altera orientação apenas da Activity e restaura ao terminar. |
| D012 | Sem adaptadores externos ou credenciais reais | Nenhuma corretora, Alpaca, IA, OpenAI, Codex SDK ou Ollama configurados. Pacote executor permanece vazio. |
| D013 | SDK Android local após aprovação; rotação temporária com restauração | SDK ausente foi instalado em `.tools`. Como o usuário não podia girar fisicamente o tablet, o script de captura rotacionou a tela e restaurou exatamente o modo anterior em `finally`. Fronteira entre configuração de teste temporária e alteração global permanente mantida. |

M0 foi formalmente aprovado. As decisões D001–D013 registram o estado histórico do M0; abaixo estão as extensões autorizadas para M1.


## M1 aprovado para implementação

| ID | Decisão | Motivo e limite |
| --- | --- | --- |
| D014 | Gerador puro com seed, início UTC e índice de candle; algoritmo `ohlcv-v1` | Uma hora virtual por candle, blocos de 24 nos regimes alta/baixa/lateral/volátil. PRNG por seed+índice, Decimal em Python 3.12. O ritmo não muda os valores. |
| D015 | Stream UUID derivado de algoritmo, seed, início, símbolo e timeframe | Reinícios retomam a última sequência/fechamento persistidos. Alterar seed/início cria outro stream, preservando o anterior. Paradas congelam o relógio virtual; não há backfill de tempo real. |
| D016 | `candles` e `system_events` no mesmo commit PostgreSQL | Evento somente visível/publicável após commit; IDs determinísticos e UNIQUE por stream/sequência e stream/tempo. Colisão com conteúdo diferente é erro. |
| D017 | Replay WebSocket pelo log persistido, polling 200 ms | Evita lacuna entre snapshot e conexão sem broker adicional. Eventos ao menos uma vez; cliente deduplica e recupera lacunas. Adequado ao único usuário/processo local. |
| D018 | Snapshot limitado 200 (máximo 500), cursor e `high_watermark` | Catch-up paginado fixa o limite superior; depois o WebSocket continua do cursor confirmado. REST 409 pede snapshot novo após troca/reset. |
| D019 | Um worker Uvicorn para ritmo da demo; lock transacional por stream | UNIQUE/idempotência e advisory lock evitam duplicação concorrente. Vários produtores acelerariam o relógio; não é uma implantação suportada no M1. |
| D020 | `CustomPainter` pequeno para os últimos 60 candles; cache de 500 | Escopo exige desenho incremental e inspeção básica, sem indicadores ou ferramentas de trading. Não adicionar biblioteca financeira ampla. `http` e `web_socket_channel` são os transportes mantidos pelo ecossistema Dart. |
| D021 | OHLC como strings decimais no JSON; doubles apenas nas coordenadas do gráfico | Evita transformar o frontend em fonte financeira oficial. Texto de inspeção exibe o decimal original; azul/lilás não representam recomendação. |
| D022 | API por dart-define e USB reverse, loopback, HTTP só em debug Android | Nenhum host hardcoded na aplicação. M1 contém leituras locais, sem autenticação pública ou credenciais. Revisar segurança antes de qualquer comando futuro. |
| D023 | Saúde 1.1 inclui simulador; heartbeat de transporte `stream.status` a cada 2 s | Estado parado/degradado/travado gera 503; socket silencioso é detectado em 8 s. Heartbeat não é evento de domínio persistido nem sinal. |
| D024 | Backoff 1/2/4/8/15 s, retomada por REST antes do WS | Preserva gráfico offline, limita chamadas repetidas e não perde candles confirmados. Sem cache persistente no aparelho: reabrir busca novo snapshot. |
| D025 | Chart em coluna rolável, fonte do sistema e botões >=48 dp | Cinco viewports com escala 1x/2x, inspeção estável enquanto chegam candles; textos do eixo/faixa ficam em widgets acessíveis. |

O painter usa a API estável [CustomPainter](https://api.flutter.dev/flutter/rendering/CustomPainter-class.html). Referências de transporte: [Flutter WebSockets](https://docs.flutter.dev/cookbook/networking/web-sockets), [web_socket_channel](https://pub.dev/packages/web_socket_channel) e [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/).

Esse era o limite do M1. A base c08ddf8 já continha BaseStrategy/Signal/RiskEngine/RiskDecision; o pedido atual autoriza corrigir sua integração e idempotência, sem ampliar M2 e sem iniciar M3.

## M2 — observabilidade autorizada em 2026-09-03

| ID | Decisão | Motivo e limite |
| --- | --- | --- |
| D036 | Preservar v1-deterministic e RiskEngine existentes | close/open determina BUY/SELL/HOLD; pausa e validade de 1h permanecem. Não introduzir políticas, comandos ou executor. |
| D037 | Reason obrigatório no domínio/DB, backfill comprovado | Explicações não pertencem ao Flutter. Só inferir motivo histórico quando versão, sinal e OHLC concordam; não reprocessar decisões. |
| D038 | GET Decisions 1.0, janela limitada e ordem pelo candle | Últimas 50 na UI; API até 200. Sem paginação ou atualização automática neste recorte. Consulta não chama motores. |
| D039 | Detalhe em rota Flutter rolável | Funciona com fontes grandes e paisagem, preserva a timeline ao voltar. Separar horários do candle, geração e avaliação. |
| D040 | HOLD SEM AÇÃO; risco histórico não autoriza ordens | Compatibilidade com RiskDecision para HOLD; exibir NONE/nenhuma execução. |
| D041 | Feed atual explicitamente distinguido de proveniência histórica | Candle legado armazena provider, não feed. Não inventar um atributo histórico a partir da configuração atual. |

## M1.5 — correções autorizadas em 2026-09-03

As decisões abaixo substituem, somente no escopo autorizado, as restrições históricas incompatíveis com Alpaca Market Data. Não alteram Flutter/FastAPI nem autorizam Trading API, executor ou ordens.

| ID | Decisão | Motivo e limite |
| --- | --- | --- |
| D026 | Apenas timeframe 1h; conversão explícita para REST 1Hour | Outros timeframes falham até validação específica. Uma chamada histórica solicita um único símbolo. |
| D027 | REST hourly nativa é a fonte canônica; WS minute bars apenas sinalizam atividade | Barras b/u nunca são persistidas como horas. A cada até 60 s, REST recupera horas fechadas, após margem adicional de 60 s. Sem agregador próprio nem suposição de que todo minuto possui negócios. |
| D028 | Identidade provider/symbol/timeframe/open_time separada da sequence | Sequence consecutiva por série é alocada no commit PostgreSQL sob advisory lock; rollback não cria lacuna. Flutter mantém cursor da série selecionada. |
| D029 | Quarentena transacional de todo o grafo Alpaca anterior | Foram encontrados candles de minuto rotulados 1h. Não se pode distinguir com confiança a origem de cada linha; archive preserva IDs/payloads e dependências, sem apresentá-los como dados válidos. Backup anterior mantido localmente. |
| D030 | Sessão regular pelo calendário XNYS local | Inclui feriados, DST e early closes sem Trading API. market_closed significa sessão regular fechada; REST pode conter pré/after-market. Não aplicar stalled do simulador à espera de horas reais. |
| D031 | ACK explícito de conexão/auth/subscrição e backoff 1/2/5/10/30 | Reset apenas após 60 s de conexão estável. Erros de credenciais/feed não entram em loop agressivo. Sem mensagens brutas contendo segredos. |
| D032 | Candle/evento/sinal/risco atômicos, duplicidade explícita e conflito fatal | Mesmo conteúdo recupera evento existente sem recalcular decisões. Alteração posterior da fonte para identidade conhecida exige investigação; não corrigir preços/decisões automaticamente. |
| D033 | NUMERIC(28,10), validação Decimal e contratos de mercado 2.0 | Preserva precisão suportada sem float; preços fora da precisão falham. Hora/sequence antigos deixam de ser compatíveis. Saúde mantém envelope 1.1. |
| D034 | Séries independentes no Flutter, até 2.000 candles, chart cronológico | Troca de ativo cancela requisições/socket anteriores e busca snapshot próprio. Timestamp de mercado e ordem de ingestão podem divergir em backfill. |
| D035 | Smoke opt-in separado de testes offline | Testes bloqueiam internet; RUN_ALPACA_SMOKE_TEST=1 autoriza smoke real limitado. Sem flag: SKIPPED. ACK não é prova de nova hora ao vivo nem da cadeia até o tablet. |
| D036 | Calendário com biblioteca dedicada e stubs locais mínimos | exchange_calendars 4.13.2 não fornece py.typed; stubs descrevem somente a API utilizada, em vez de desabilitar mypy. alpaca-py removido por não ser necessário. |

Fontes oficiais consultadas:

- [Alpaca Stock Bars](https://docs.alpaca.markets/us/reference/stockbars): símbolos, timeframe, ordenação e paginação.
- [Alpaca real-time stock data](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data): bars de minuto e updatedBars por negócios atrasados.
- [Alpaca streaming market data](https://docs.alpaca.markets/us/docs/streaming-market-data): autenticação, assinatura e códigos de erro.
- [NYSE horários e calendários](https://www.nyse.com/trade/hours-calendars): sessão regular e encerramentos antecipados.
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars): calendário XNYS local.

Limitação explícita: margem de 60 s reduz correções tardias, mas não promete imutabilidade futura do provedor. Conflitos recebidos interrompem a ingestão. Feed/permissões, latência e nova hora real no tablet ainda exigem smoke e demonstração autorizados.
