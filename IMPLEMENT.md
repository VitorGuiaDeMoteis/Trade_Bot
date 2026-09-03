# IMPLEMENT — regras para o Codex

## Missão

Implementar o Trading Bot Dashboard v0.1 exatamente conforme `PRODUCT.md`, `ARCHITECTURE.md` e `MILESTONES.md`, avançando um marco por vez e mantendo o projeto sempre executável.

## Forma de trabalho

1. Leia todos os documentos antes de editar.
2. Antes de cada marco, apresente um plano curto e os arquivos que serão alterados.
3. Implemente somente o marco atual.
4. Execute formatação, lint, testes e smoke test relevantes.
5. Se uma validação falhar, corrija antes de avançar.
6. Atualize `docs/STATUS.md` com progresso, decisões, comandos e pendências.
7. Não aumente o escopo silenciosamente.
8. Pare e peça decisão quando uma escolha alterar produto, segurança, corretora ou risco.

## Restrições obrigatórias

- Sem dinheiro real.
- Sem integração com corretora antes da conclusão da v0.1.
- Sem credenciais reais.
- Sem IA enviando ordens.
- Sem processamento de candle ainda aberto.
- Sem valores monetários em `float`.
- Sem ordem sem idempotência.
- Sem endpoint que permita saque.
- Sem botão visual que não execute a ação correspondente.
- Sem esconder falhas ou transformar erro em sucesso silencioso.

## Qualidade

- Backend com tipagem, validação e testes.
- Contratos de API versionados.
- Migrações de banco reproduzíveis.
- Código de domínio independente do framework quando razoável.
- Datas em UTC no backend.
- Logs estruturados com `correlation_id`.
- Acessibilidade básica e alvos de toque adequados no Flutter.
- Layout testado em telefone e tablet, retrato e paisagem.
- Estados de loading, vazio, erro, offline e degradado implementados.

## Decisões arquiteturais

- Começar com monólito modular no backend; não criar microserviços físicos prematuramente.
- Usar WebSocket apenas para eventos; snapshots e histórico vêm por REST.
- PostgreSQL é a fonte de verdade.
- O frontend nunca calcula saldo oficial.
- O simulador deve permitir seed e relógio controlável.
- Estratégia, risco e executor são módulos separados.
- Eventos persistidos antes de serem considerados concluídos.

## Documentação permanente

Criar e manter:

- `docs/STATUS.md` — feito, atual, próximo e bloqueios;
- `docs/DECISIONS.md` — decisões arquiteturais e justificativas;
- `docs/RUNBOOK.md` — execução, testes, reset e recuperação;
- `docs/SECURITY.md` — segredos, ameaças e controles;
- `docs/DEMO.md` — roteiro para demonstrar cada marco.

## Regra de conclusão

Um marco só está concluído quando suas entregas existem, todos os critérios de aceite correspondentes foram verificados e os comandos usados para verificar estão registrados no `STATUS.md`.

