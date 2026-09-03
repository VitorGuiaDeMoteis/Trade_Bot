# Segurança — M1

## Superfície atual

Monitoramento local de candles fictícios. Saúde, OpenAPI, histórico REST e WebSocket de leitura. Sem comandos de trading, autenticação pública, corretora, IA, ordens, posições ou lucro. Estratégia, risco e execução permanecem fronteiras reservadas.

## Controles presentes

- API em 127.0.0.1 e Compose vinculado a loopback. Não usar 0.0.0.0, LAN ou Internet.
- Tablet acessa por adb reverse; endpoint obrigatório por dart-define, sem host padrão no Dart.
- Android permite HTTP apenas no manifest de debug. Release requer HTTPS; não é alvo de distribuição deste marco.
- WebSocket rejeita Origin externo quando presente. Não constitui autenticação; cliente nativo local sem Origin é permitido.
- Nenhuma chave externa. .env, SDK, logs e builds ignorados; .env.example somente com valores fictícios.
- SQLAlchemy com parâmetros. REST até 500; WS em lotes de 100. Timeouts de conexão/pool/consultas.
- Candles/eventos atômicos, IDs determinísticos, UNIQUE, checks OHLCV e UTC. Replay não cria nova linha.
- Cliente valida versão/invariantes antes de atualizar gráfico; lacunas iniciam recuperação.
- /health 503 para banco indisponível ou simulador não operacional. Sem DSN/stack trace no erro REST.
- Logs JSON UTC com correlation_id. Não registrar cabeçalhos, corpo, senha ou query string. Usar --no-access-log.
- OHLC em strings decimais; double apenas para coordenadas de desenho. Nenhum cálculo de dinheiro no Flutter.
- Migrações destrutivas testadas somente no banco descartável trading_bot_test, porta 5433. Volume dev preservado.
- Testes de fronteira protegem domínio/gerador da camada HTTP e mantêm estratégia/risco/execução separados.

## Limites deliberados

Sem login, TLS local, quotas por usuário, auditoria de produção ou proteção contra usuários maliciosos do próprio computador. Não publicar o serviço. Senha fictícia somente para PostgreSQL de desenvolvimento isolado. Android debug.

Antes de comandos futuros, revisar autenticação/autorização. Execução futura exigirá decisão determinística de risco e idempotência; frontend não autoriza operação nem é fonte de saldo. Nada disso foi antecipado.

Banco cresce enquanto simulador está ativo. Não há retenção automática; não apagar volume para recuperar falhas. Intervalo configurável reduz geração.

## Dispositivo e recuperação

Sem mudança permanente de SDK/PATH/rotação. Capturas usam rotação temporária e finally. Autorizações do instalador Android devem ser confirmadas no aparelho, sem desativar proteções.

Diretórios preservados da recuperação M0:
- C:/Users/vitor/AppData/Local/Docker/run.stale-20260903103306
- C:/Users/vitor/AppData/Local/Docker/run.stale-20260903103549
- C:/Users/vitor/AppData/Local/docker-secrets-engine.stale-20260903103549

Não usar factory reset/exclusão ampla de AppData como rotina. Se um segredo real for introduzido por engano, revogar na origem e remover do histórico antes de publicar. Não compartilhar logs brutos de outros apps do tablet.

