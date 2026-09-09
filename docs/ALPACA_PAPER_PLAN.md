# Plano de Integração: Alpaca Paper Trading (M7)

Este documento define os critérios, restrições e arquitetura para a integração da Alpaca Trading API em ambiente isolado (Paper Trading), conforme as diretrizes do M6 e as lições aprendidas até a estabilização v0.1.

## 1. Isolamento e Segurança (Obrigatório)
A arquitetura proíbe terminantemente qualquer risco de uso acidental de fundos reais.
- **Endpoint Exclusivo:** O cliente da Alpaca deve ser *hardcoded* para utilizar a URL base do Paper Trading (`paper-api.alpaca.markets`). Nenhuma injeção de configuração, variável de ambiente ou chave do `.env` pode sobrescrever a URL base para apontar para `api.alpaca.markets`. Nenhuma URL LIVE deve estar sequer presente na base do Adapter.
- **Conta Segregada:** As chaves configuradas serão validadas para garantir que são exclusivas do ambiente Paper.
- **Nenhum Segredo Vazado:** Nenhuma credencial será exposta via logs (nem debug), retornos da API REST ou tráfego acessível pelo Flutter. O backend deve atuar como um *gateway* cego e seguro.

## 2. Broker Adapter Isolado & Autoridade
O núcleo de execução local (`PaperExecutor`) continuará intacto. Um novo componente, `AlpacaPaperAdapter`, deverá implementar a mesma interface abstrata de execução. 
- O adaptador será o responsável exclusivo por traduzir o modelo interno de ordens para a API da Alpaca e vice-versa.
- Não haverá lógica de negócio vazada para dentro do adapter.
- O Observer **não possui** autoridade financeira. Ele apenas produz informações, alertas ou recomendações informativas (como HOLD). Decisões de emitir ou bloquear ordens pertencem estritamente e exclusivamente às fronteiras do `Strategy`, `RiskEngine`, `PaperExecutor` e o respectivo broker adapter.

## 3. Idempotência e Comportamento de Envio
O envio de operações ao ambiente Paper será estritamente determinístico:
- **Client Order IDs:** Toda ordem enviada deve incluir um `client_order_id` gerado deterministicamente localmente antes do submit.
- **Persistência de Intent:** A intenção de ordem, junto com seu estado inicial de `SUBMITTING`, deve ser persistida localmente no banco ANTES da tentativa de chamada externa.
- **Timeout / Conexão Perdida:** Nenhuma ordem deve ser re-enviada "às cegas" após um timeout. Antes de qualquer *retry*, o sistema DEVE consultar a Alpaca pelo `client_order_id` e consultar as ordens recentes. Apenas se houver prova cabal e reconciliada de que a ordem original NÃO existe na corretora, o envio poderá ser retentado.

## 4. Gerenciamento de Estados
O sistema interpretará e armazenará de forma mapeada cada estado retornado pela Alpaca:
- Estados reconhecidos: `new`, `accepted`, `pending_new`, `partially_filled`, `filled`, `canceled`, `pending_cancel`, `rejected`, `expired`, `replaced`.
- Estados inesperados também deverão ser persistidos (ex: em campo de meta) e logados, e a ordem considerada em atenção (não concluída).
- **Atenção aos Fills:** Não deve haver invenção de execução ("fill local") se o dado não tiver vindo como confirmação da Alpaca Paper.

## 5. Partial Fills
Como a ordem pode não ser integralmente executada:
- A cada *fill* real e confirmado, este evento deverá ser persistido no banco local.
- O saldo da posição deve ser incrementado progressivamente de forma totalmente reconciliável com a quantidade total informada pela corretora.
- O sistema não deve duplicar o registro de fills e deve sempre continuar acompanhando o saldo da quantidade restante (*remaining quantity*).

## 6. Cancelamentos
- O fluxo de requisição de cancelamento não deve ser interpretado como um cancelamento garantido.
- O sistema deverá aguardar ativamente que o estado `canceled` seja confirmado.
- O sistema deverá possuir rotinas robustas para reconciliar e computar fills parciais (partially filled) que possam vir a ocorrer concomitantemente durante uma janela de `pending_cancel`.

## 7. PAUSED/STOP/DEGRADED e Limites
As interrupções financeiras do sistema (`PAUSED`, estado `DEGRADED`, acionamento de `STOP`) devem atuar de maneira firme:
- Tais estados bloqueiam preventivamente novos submits de ordens. Nenhuma nova chamada à Alpaca visando criar ordem será autorizada enquanto o estado persistir.
- Entretanto, chamadas de **reconciliação** e monitoramento (para recuperar estados, posições ativas ou status das ordens que já estavam no book da corretora) permanecem permitidas de forma a garantir sincronia, não importando a degradação local.
- Shorting continuará não permitido por arquitetura para reduzir as variáveis na gestão de riscos e alavancagem.
