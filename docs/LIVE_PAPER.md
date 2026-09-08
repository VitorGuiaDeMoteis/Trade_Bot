# Live Paper

O modo `alpaca_paper` usa exclusivamente `https://paper-api.alpaca.markets` e
dinheiro fictício da conta Paper. O endpoint de trading real não é configurável
pelo aplicativo.

O runtime aceita apenas decisões `APPROVED`, sinais `BUY` ou `SELL` da estratégia
`v2-15m-baseline` e candles Alpaca fechados de 15 minutos. Antes de reservar uma
ordem, exige banco atualizado, runtime reconciliado, controle armado por CLI,
provider conectado, candle Alpaca de 1 minuto recente, clock da corretora aberto
dentro da sessão regular de Nova York e ausência de conflito no símbolo.

`BUY` abre somente posição long, usa ações inteiras e limita o notional ao menor
valor entre 10% do equity e o cash. `SELL` existe apenas para fechar integralmente
uma posição long inteira. Não há margin, short ou pyramiding.

Cada decisão gera um `client_order_id` determinístico `agy-<uuid5 hex>`. A reserva
local é persistida antes do POST. Em resposta perdida, o restart consulta a ordem
pelo mesmo identificador e não repete o POST. Fills remotos cumulativos são gravados
somente como deltas locais.

O comando de ARM permanece exclusivamente na CLI e requer autorização operacional
explícita. Nenhum ARM ou POST real deve ser executado durante gates automatizados.
