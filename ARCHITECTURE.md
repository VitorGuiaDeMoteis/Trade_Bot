# ARCHITECTURE — Trading Bot Dashboard v0.1

## Objetivo técnico

Construir uma fatia vertical local e simulada que percorra todo o fluxo: geração de candles, persistência, estratégia, risco, execução simulada, eventos em tempo real e apresentação mobile-first.

## Componentes

Recorte implementado M5: o Observer recebe DTO saneado através de adapters
confiáveis de leitura e grava somente sua auditoria. Core não recebe Settings,
engine SQL, executor ou controles. Fake local e transporte OCI sem rede/volumes;
nenhum modelo vendor integrado. [Contratos e fluxo](docs/M5_CORE.md),
[fronteiras e premissas](docs/M5_THREAT_MODEL.md). Interface Flutter M5 pendente.

### `mobile_app`

Aplicativo Flutter responsivo.

Responsabilidades:

- consultar snapshots por REST;
- receber eventos por WebSocket;
- exibir estado, gráficos e histórico;
- enviar apenas STOP local; retomada/reset permanecem CLI;
- nunca conter segredo de corretora;
- nunca calcular a fonte oficial do saldo ou do risco.

### `api`

FastAPI responsável pela borda do sistema.

Responsabilidades:

- endpoints REST;
- WebSocket autenticado;
- validação de comandos;
- health checks;
- serialização de contratos;
- publicação de atualizações para o dashboard.

### `market_simulator`

Gera candles reproduzíveis usando uma semente configurável.

Responsabilidades:

- produzir OHLCV válido;
- simular regimes de alta, baixa, lateralização e volatilidade;
- controlar velocidade da simulação;
- permitir replay determinístico.

### `strategy_engine`

Primeira estratégia simples e determinística.

Responsabilidades:

- consumir candles fechados;
- produzir `BUY`, `SELL` ou `HOLD`;
- registrar indicadores e justificativas objetivas;
- identificar versão da estratégia;
- não acessar carteira nem corretora diretamente.

### `risk_engine`

Autoridade final antes da execução.

Responsabilidades:

- validar modo do sistema;
- bloquear se pausado ou degradado;
- validar perda diária e exposição;
- calcular tamanho da posição;
- impedir duplicidade;
- registrar aprovação ou bloqueio e motivo.

### `paper_executor`

Simulador de corretora.

Responsabilidades:

- aceitar apenas decisões autorizadas pelo risco;
- simular taxas, slippage, fills e posições;
- usar chave de idempotência;
- atualizar saldo e posições;
- publicar eventos de ordem e execução.

### `backtesting` (núcleo M4)

Orquestrador offline de Strategy/Risk/PaperExecutor, sem lógica financeira paralela.
Congela candles do PostgreSQL em transação somente leitura, ordena grupos de OPEN
cross-asset, executa sinais anteriores e só então revela CLOSEs à estratégia.
Publica manifest e relatório JSON atômicos, com versões, hashes, métricas e modo
BACKTEST. Não escreve na carteira corrente nem expõe comandos remotos. Replay
visual consome os frames do relatório pela API somente leitura, sem recalcular
finanças. [Contrato e invariantes](docs/M4_CORE.md); [aceite físico](docs/M4_ACCEPTANCE.md).

### `database`

PostgreSQL como fonte persistente de verdade.

Entidades iniciais:

- `candles`;
- `strategy_signals`;
- `risk_decisions`;
- `orders`;
- `fills`;
- `positions`;
- `portfolio_snapshots`;
- `system_events`;
- `system_controls`;
- `strategy_versions`.

## Fluxo principal

1. Simulador fecha um candle.
2. Candle é validado e persistido.
3. Estratégia recebe o candle persistido.
4. Estratégia gera um sinal versionado.
5. Risco aprova ou bloqueia o sinal.
6. Executor processa apenas uma decisão aprovada.
7. Ordem, fill, posição e carteira são persistidos.
8. API publica os eventos no WebSocket.
9. Aplicativo atualiza as telas.

## Eventos da v0.1

Todos possuem `event_id`, `event_type`, `occurred_at`, `schema_version`, `correlation_id` e `payload`.

- `market.candle.closed`;
- `strategy.signal.created`;
- `risk.decision.created`;
- `paper.order.created`;
- `paper.order.filled`;
- `position.updated`;
- `portfolio.updated`;
- `system.mode.changed`;
- `system.health.changed`;
- `system.alert.created`.

## Contrato mínimo de sinal

```json
{
  "signal_id": "uuid",
  "strategy_id": "baseline-trend",
  "strategy_version": "0.1.0",
  "symbol": "TEST",
  "timeframe": "1h",
  "action": "BUY",
  "confidence": 0.63,
  "generated_at": "2026-09-03T12:00:00Z",
  "valid_until": "2026-09-03T13:00:00Z",
  "reasons": ["fast_average_above_slow_average"],
  "input_candle_id": "uuid"
}
```

## Regras de confiabilidade

- Processar somente candles fechados.
- Usar UTC em backend e banco; converter apenas na interface.
- Valores monetários usam decimal, nunca ponto flutuante binário.
- Toda ordem possui chave de idempotência única.
- Reiniciar serviços não pode recriar ordens já processadas.
- Eventos inválidos vão para log e alerta, não para execução.
- Ausência de dados, dados atrasados ou serviço degradado resultam em bloqueio.
- O sistema deve falhar fechado: na dúvida, não abre nova posição.
- Stop e limites não dependem de IA ou do dashboard.

## Segurança

- Nenhum segredo no repositório.
- `.env.example` contém somente nomes e valores falsos.
- API não retorna segredos.
- Comandos de controle exigem autenticação.
- Logs removem tokens e dados sensíveis.
- Quando houver corretora, chaves devem permitir negociação, nunca saque.
- Processo da IA não recebe credenciais da corretora.

## Integração futura com Codex/IA

O serviço `analyst_agent` será adicionado depois da estratégia-base.

Ele poderá:

- ler snapshots saneados do mercado e da carteira;
- classificar regime de mercado;
- produzir relatórios e explicações estruturadas;
- selecionar entre estratégias previamente aprovadas;
- sugerir estratégias candidatas para pesquisa.

Ele não poderá:

- acessar o executor diretamente;
- alterar limites globais;
- publicar uma estratégia nova em produção;
- ler credenciais;
- executar comandos de saque;
- transformar texto livre em ordem.

Saídas devem obedecer a JSON Schema. Falha, timeout, resposta inválida ou baixa confiança resultam em `HOLD` e alerta.

## Estrutura recomendada do repositório

```text
trading-bot/
  apps/
    mobile_app/
  services/
    api/
    market_simulator/
    strategy_engine/
    risk_engine/
    paper_executor/
  packages/
    contracts/
    domain/
  infrastructure/
    docker/
  docs/
  tests/
  docker-compose.yml
  .env.example
  README.md
```

Na primeira implementação, os serviços Python podem compartilhar um único processo modular para reduzir complexidade. As fronteiras lógicas devem permanecer claras para futura separação.

