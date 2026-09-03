# Status — Trading Bot Dashboard v0.1

## M1.5 — em validação

Base: main, c08ddf87216efb2e09bea55e497ec6439392d8ef. Checkout inicialmente limpo. Remoto informado pelo usuário e origin atual resolveram para o mesmo commit. Correções autorizadas: dados reais + análise/decisão simulada. Sem Trading API, ordens, executor paper ou avanço de marco.

## Histórico M0

Aceite antigo em [STATUS-M0](STATUS-M0.md). Seus números de testes, revisão 0001_m0 e capturas descrevem exclusivamente M0. Não são validação atual.

## Validação M1

Evidências históricas em docs/evidence/m1-*. A integração anterior do simulador passou REST/WS e retomada após interrupção. Não comprova Alpaca. [DEMO](DEMO.md) ainda contém o roteiro histórico M1 e será revisado junto às correções.

## Validação M1.5 — diagnóstico inicial executado em 2026-09-03

| Verificação | Resultado observado |
| --- | --- |
| git status / HEAD / ls-remote | Limpo; main e remotos no commit c08ddf8 |
| Ruff check | Falhou: 46 erros |
| mypy | Falhou: 11 erros em 5 arquivos, 33 arquivos examinados |
| pytest -m "not integration", provider forçado simulator | 32 passaram; 10 PostgreSQL não executados nessa chamada |
| Flutter analyze | Falhou: 9 problemas, incluindo referências a enums removidos |
| adb devices / flutter devices | Xiaomi 23073RPBFG / 1791a20e / Android 15 detectado |
| Docker Compose ps | Engine Linux indisponível inicialmente; inicialização em diagnóstico |
| Credenciais locais | Variáveis presentes; nenhum valor exibido |
| RUN_ALPACA_SMOKE_TEST | Desabilitado; acesso real não validado nesta etapa |

Logs de diagnóstico em .artifacts/m15-baseline-*. Aviso de depreciação Starlette/AnyIO preservado, sem supressão.

Problemas confirmados por leitura: histórico ignora símbolo/timeframe; minute bars rotuladas como 1h; sequence por timestamp incompatível com cliente; ValueError ignorado; status conflitando com runtime; fixtures e documentação desatualizados. Ausência de testes dedicados suficientes ao provider.

## Plano em execução

1. Identidade de mercado separada do cursor interno consecutivo por série.
2. 1h fechado obtido da REST 1Hour; minute bars WS apenas notificam atualização.
3. Configuração, handshake, estados, calendário, backoff e falhas explícitas.
4. Persistência idempotente incluindo evento/sinal/decisão, replay e consulta por símbolo.
5. Flutter com séries independentes e testes de troca/reconexão.
6. Fakes Alpaca sem internet, PostgreSQL real, qualidade, documentação e pequenos commits.

Os resultados finais serão adicionados somente após execução. M1.5 não está declarado concluído. Smoke real será mantido separado e condicionado à autorização explícita RUN_ALPACA_SMOKE_TEST=1.

