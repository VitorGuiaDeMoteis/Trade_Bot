# PRODUCT — Trading Bot Dashboard v0.1

## Visão

Criar um produto de trading automatizado transparente e mobile-first. O usuário deve conseguir entender em poucos segundos se o bot está saudável, quanto ganhou ou perdeu, qual risco está assumindo e por que tomou ou recusou uma decisão.

A v0.1 é um laboratório de engenharia e validação. Ela não promete lucro, não movimenta dinheiro real e não é oferecida a clientes.

## Usuários iniciais

### Usuário principal

Vitor, proprietário e primeiro operador. Usará principalmente um tablet enquanto trabalha e também celular e computador.

### Usuários futuros

Sócios e amigos que precisam acompanhar o sistema rapidamente durante intervalos do trabalho. Cada usuário deverá ter sua própria conta, saldo, limites e histórico. Multiusuário não faz parte da v0.1, mas a arquitetura não deve impedir essa evolução.

## Princípios de produto

1. Estado compreensível em até cinco segundos.
2. Modo `SIMULADO` ou `REAL` sempre evidente; a v0.1 mostra apenas `SIMULADO`.
3. Toda ação possui horário, origem, estratégia, justificativa e resultado.
4. A interface mostra decisões bloqueadas, não apenas operações executadas.
5. Segurança e rastreabilidade têm prioridade sobre quantidade de recursos.
6. IA não é apresentada como garantia de retorno.
7. O produto deve funcionar bem em orientação retrato e paisagem no tablet.

## Navegação da v0.1

### 1. Resumo

Tela para consulta rápida:

- status geral: operando, pausado, degradado ou offline;
- selo grande `SIMULADO`;
- saldo atual;
- P&L do dia e acumulado;
- drawdown atual e máximo;
- risco diário consumido;
- posições abertas;
- última decisão e justificativa curta;
- horário da última atualização;
- botão de emergência `Pausar novas operações`.

### 2. Mercado

- gráfico de candles;
- seletor de período;
- volume;
- indicadores habilitados;
- marcações de entrada e saída;
- marcações de sinais recusados;
- estratégia ativa e regime de mercado.

### 3. Decisões

Linha do tempo com:

- sinal produzido;
- dados que sustentaram o sinal;
- decisão do motor de risco;
- motivo de aprovação ou bloqueio;
- ordem simulada e resultado, quando existente.

### 4. Histórico

- operações encerradas;
- lucro/prejuízo;
- duração;
- estratégia e versão;
- taxas e slippage simulados;
- filtros por ativo, período e resultado.

### 5. Sistema

- saúde do backend, banco, stream e simulador;
- última coleta de dados;
- erros recentes;
- versão da aplicação e estratégia;
- estado do botão de emergência.

## Escopo funcional da v0.1

- autenticação local simplificada para um usuário;
- dados de mercado simulados reproduzíveis;
- atualização em tempo real;
- carteira e posições simuladas;
- uma estratégia determinística simples;
- motor de risco determinístico;
- execução simulada idempotente;
- trilha completa de auditoria;
- dashboard responsivo;
- pausa e retomada de novas operações;
- testes automatizados dos fluxos críticos.

## Fora do escopo

- dinheiro real;
- integração real com corretora;
- saque ou depósito;
- estratégias criadas e publicadas automaticamente por IA;
- copy trading;
- cobrança ou assinaturas;
- cadastro público;
- múltiplos usuários;
- notificações push;
- alta frequência ou scalping;
- aconselhamento financeiro ao público.

## Métricas da v0.1

- nenhuma ordem duplicada após reinício;
- nenhuma operação após o botão de pausa;
- todos os sinais com decisão de risco registrada;
- dashboard atualiza sem recarregar a página;
- estado offline/degradado detectado e exibido;
- backtest reproduzível com a mesma entrada e configuração;
- taxas e slippage presentes nos resultados;
- testes dos controles críticos passando.

## Direção visual

- tema escuro, profissional e legível;
- verde apenas para resultado positivo e estado saudável;
- vermelho apenas para perdas, risco ou falhas;
- âmbar para alertas e modo degradado;
- números grandes na tela de resumo;
- gráficos secundários acessíveis por aprofundamento;
- sem excesso de indicadores ou aparência de cassino.

