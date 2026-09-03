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

M2 permanece sem autorização e sem implementação.
