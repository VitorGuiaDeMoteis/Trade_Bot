# Segurança M4 — pesquisa isolada (2026-09-04)

Backtest não tem endpoint de execução, conexão externa, credencial própria nem
acesso de escrita à carteira. Freeze usa transação PostgreSQL READ ONLY; run lê
somente JSON local, sem carregar Settings/.env. Todos os resultados são BACKTEST.
O controle STOP e a pausa da carteira corrente permanecem com o contrato M3.
Backtesting histórico isolado não chama resume/reset e não aumenta sua autoridade.

Checksum, validação temporal/OHLCV/Decimal e reconciliação falham de forma explícita;
nenhum resultado parcial é publicado. Hashes não substituem autenticidade frente
a um atacante local com permissão de escrita. JSON não executa código. Não incluir
credenciais nos arquivos ou versionar `.env`; manifests e relatórios completos
ficam em `.artifacts` ignorado pelo Git. Nenhuma Trading API ou IA foi adicionada.

[Limites e evidências](M4_CORE.md). Entradas posteriores nesta página são históricas.

---

# Segurança M3 — STOP local (2026-09-04)

A regra atual do controle de pausa está em [M3_STOP](M3_STOP.md). STOP não usa mais
Bearer: aceita apenas POST vazio de peer loopback/Host local com marcador público,
sem Origin, Referer, Sec-Fetch ou headers de proxy. Uvicorn em 127.0.0.1 com
--no-proxy-headers, Xiaomi via adb reverse, sem proxy/LAN/publicação.

Um processo local ou outro aplicativo com acesso ao túnel pode PARAR; esse risco
residual de indisponibilidade é aceito porque não aumenta autoridade. Resume/reset
continuam CLI. Nunca reutilizar essa permissão para executar ou retomar operações.
Sem segredo no Flutter/APK/Git e sem Trading API. O relatório financeiro anterior
é histórico quanto à autenticação Bearer de STOP; a proteção de execução permanece.

---

# Segurança — M2 / M1.5

## Escopo autorizado

Dados reais de mercado + análise/decisão hipotética observável no M2. A integração existente Candle → BaseStrategy → Signal → RiskEngine → RiskDecision permanece local. Nenhuma ordem, carteira, executor paper, Trading API, dinheiro real ou IA com autoridade de execução. M3 não autorizado.

Decisions é GET somente leitura, com limite 1..200, série configurada, consulta SQL parametrizada e resposta restrita ao contrato público. Não retorna Settings, chaves ou DSN. APPROVED é um registro histórico de risco; não autoriza operação. HOLD permanece SEM AÇÃO. Falha no banco retorna 503, sem detalhes de conexão. Arquivo de quarentena não participa da consulta.

Migração 0007 preserva IDs, timestamps e decisões. Backfill de reason só infere a regra comprovada por versão + sinal + candle; casos desconhecidos têm explicação de legado indisponível. Backup prévio é local e ignorado pelo Git.

Alpaca utiliza exclusivamente data.alpaca.markets e stream.data.alpaca.markets. O SDK alpaca-py não é necessário e foi removido. HTTP e WebSocket diretos têm timeouts e erros classificados. Calendário XNYS é local; não consulta clock/calendar da Trading API.

## Configuração e segredos

.env é local e ignorado; .env.example contém nomes seguros e chaves vazias. ALPACA_API_KEY_ID e ALPACA_API_SECRET_KEY são SecretStr no backend e obrigatórios com provider=alpaca. Erros de validação ocultam valores de entrada. Nunca colocar segredos no Flutter, dart-define, URL, log ou chat.

Logs estruturados contêm códigos controlados, UTC e correlation_id. Não registrar respostas de autenticação, headers ou texto bruto de exceções externas. Desabilitar access log do servidor. Não compartilhar logcat completo: outros aplicativos do aparelho podem aparecer nele.

Smoke test exige RUN_ALPACA_SMOKE_TEST=1; sem opt-in retorna SKIPPED antes de criar provider. Testes automatizados bloqueiam HTTP/WS externos e usam fakes; PostgreSQL de teste fica em localhost:5433.

## Superfície local

API 127.0.0.1, PostgreSQL Compose em loopback e tablet via adb reverse. Sem autenticação pública/TLS local: não publicar em LAN/Internet. Android permite HTTP somente em debug. Origin externo no WebSocket é rejeitado, mas isso não constitui autenticação.

Consultas parametrizadas, limites REST/WS, pools/timeouts e constraints de integridade. Preços são Decimal no backend, strings no contrato e doubles somente para desenho. Somente candles fechados alimentam estratégia; decisões existentes são simuladas e não autorizam execução.

Duplicatas não repetem sinais/risco. Conteúdo divergente falha explicitamente. Transações atômicas incluem as quatro tabelas. Precisão fora da capacidade do banco é rejeitada, não arredondada silenciosamente.

## Preservação de dados e dispositivos

Migração 0006_m15_integrity move o grafo Alpaca legado para legacy_market_archive, com payload completo, motivo e UUID original. Backup local pré-migração em .artifacts/m15-before-quarantine.sql. Esse arquivo fica ignorado e não foi publicado. Quarentena é evidência não validada; não reaproveitar automaticamente como histórico correto.

Downgrade com novos candles Alpaca é bloqueado para não misturá-los ao legado. Downgrades destrutivos gerais pertencem ao banco descartável de testes. Não apagar volumes para recuperar falhas.

SDK e PATH são configurados apenas na sessão. Captura do tablet modifica temporariamente a rotação e restaura modo/valor anteriores em finally. Não desativar proteção do instalador Android.

Docker 4.68.0 voltou a falhar com sockets inacessíveis. Recuperação preservou diretórios, sem factory reset ou remoção de volumes:

- C:/Users/vitor/AppData/Local/Docker/run.stale-20260903103306
- C:/Users/vitor/AppData/Local/Docker/run.stale-20260903103549
- C:/Users/vitor/AppData/Local/docker-secrets-engine.stale-20260903103549
- C:/Users/vitor/AppData/Local/Docker/run.stale-20260903193627
- C:/Users/vitor/AppData/Local/docker-secrets-engine.stale-20260903193627

Esses caminhos não devem ser apagados automaticamente. Não há distribuição de produção, execução financeira ou garantia de qualidade do feed real sem as validações pendentes do STATUS.
