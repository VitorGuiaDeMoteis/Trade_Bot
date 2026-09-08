# Evidências do runtime Live Paper

## Invariantes

- `execution_ready=false` até reconciliar banco, conta, clock, posições e ordens.
- Conta inválida, posição short/duplicada, estado remoto desconhecido, divergência
  de identidade ou divergência de fill bloqueiam execução.
- A ordem remota deve corresponder ao símbolo, lado e quantidade da reserva local.
- Estados suportados: `pending_new`, `accepted`, `new`, `partially_filled`,
  `filled`, `canceled`, `rejected` e `expired`.
- `POST success` não significa fill.
- Para quantidade cumulativa remota `0 -> 2 -> 5`, os fills locais são `2` e `3`;
  nova reconciliação em `5` não acrescenta fill.
- Uma ordem `filled` precisa ter quantidade cumulativa igual à solicitada.
- O banco rejeita quantidade solicitada zero, estado inválido, fill sem preço e
  fill completo inconsistente.

## Cobertura PostgreSQL

Os testes usam somente `trading_bot_test` em `127.0.0.1:5433`. Eles cobrem BUY,
SELL, partial fill, restart após perda de resposta, concorrência, no-data, stale,
provider degradado, mercado fechado, isolamento por símbolo, 100 decisões históricas,
lifespan FastAPI e endpoints dashboard/orders/fills.

O ARM final e as leituras reais da conta Alpaca Paper permanecem fora dos testes.
