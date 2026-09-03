# MILESTONES — Trading Bot Dashboard v0.1

## M0 — Fundação

### Entregas

- monorepo inicial;
- backend FastAPI executável;
- aplicativo Flutter executável;
- PostgreSQL no Docker Compose;
- migrações de banco;
- configuração de lint e testes;
- documentação de execução local.

### Aceite

- `docker compose up` inicia dependências;
- backend responde em `/health`;
- aplicativo abre em viewport de celular e tablet;
- testes e linters iniciais passam;
- nenhum segredo real está versionado.

## M1 — Fatia vertical visual

### Entregas

- simulador de candles com semente fixa;
- persistência de candles;
- endpoint de histórico;
- WebSocket de eventos;
- gráfico atualizando sem recarregar;
- indicador de conexão e última atualização.

### Aceite

- mesma semente gera os mesmos candles;
- reconectar o aplicativo recupera o snapshot correto;
- candle não aparece duplicado após reinício;
- layouts de telefone e tablet não apresentam overflow.

## M2 — Estratégia-base e decisões

### Entregas

- estratégia determinística versionada;
- sinais `BUY`, `SELL` e `HOLD`;
- motor de risco;
- timeline de decisões;
- justificativas legíveis na interface.

### Aceite

- cada candle processado possui no máximo um sinal por versão;
- cada sinal possui exatamente uma decisão de risco;
- sinais vencidos são bloqueados;
- sistema pausado não autoriza operações.

## M3 — Carteira e execução simulada

### Entregas

- executor paper;
- saldo, ordens, fills e posições;
- taxas e slippage configuráveis;
- P&L realizado e não realizado;
- resumo mobile completo.

### Aceite

- valores monetários reconciliam com histórico de fills;
- reinício não duplica ordens;
- ordem rejeitada não altera saldo;
- botão de pausa impede novas ordens;
- posições abertas continuam visíveis após reinício.

## M4 — Backtesting e replay

### Entregas

- backtest usando o mesmo domínio da execução simulada;
- métricas: retorno, drawdown, quantidade de operações, taxa de acerto, lucro médio, perda média e profit factor;
- replay visual de uma execução;
- exportação de relatório.

### Aceite

- mesmo dataset e configuração produzem resultado idêntico;
- taxas e slippage afetam o resultado;
- testes evitam look-ahead básico;
- dashboard diferencia claramente backtest de execução corrente.

## M5 — Codex analista em modo observador

### Entregas

- snapshot saneado para análise;
- execução isolada do Codex/local model;
- saída validada por JSON Schema;
- relatório de regime, riscos e observações;
- status e versão do analista no dashboard.

### Aceite

- IA não possui credenciais da corretora;
- IA não chama o executor;
- resposta inválida ou timeout gera alerta e `HOLD`;
- toda análise registra modelo, versão do prompt e dados de entrada;
- desligar a IA não interrompe controles de risco existentes.

## M6 — Estabilização da v0.1

### Entregas

- testes end-to-end;
- teste de reinício e recuperação;
- tratamento de dados atrasados;
- observabilidade e logs estruturados;
- documentação final da v0.1;
- demonstração gravável em celular/tablet.

### Aceite

- fluxo completo funciona continuamente por sete dias em simulação;
- nenhuma ordem duplicada;
- nenhuma operação durante pausa ou estado degradado;
- falhas relevantes ficam visíveis na interface;
- projeto pode ser iniciado seguindo apenas o README.

## Depois da v0.1

1. Integração com Alpaca Paper Trading.
2. Comparação entre simulador local e fills do paper broker.
3. Piloto pessoal com capital pequeno, apenas após critérios específicos.
4. Contas independentes para sócios.
5. Segurança multiusuário e auditoria ampliada.
6. Revisão jurídica e regulatória antes de comercialização.

