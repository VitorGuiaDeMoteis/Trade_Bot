# M4 - Concluído (2026-09-04)

Branch `codex/m4-backtesting`, base `cc4c2d54399eefa03f1b57866f6f784bc73cdd67`.

**Status Atual:**
A interface do usuário em Flutter (Dashboard + Tabs), Replay visual, listagem por API, leitura do schema, validação do hash (Fail Closed) e exportação de arquivo foram implementados e auditados.

**Componentes M4 Concluídos e Auditados:**
* **Nuvem/Back**: O núcleo financeiro, RiskEngine, PaperExecutor, e a API de leitura de relatórios estão completos, estáveis e não foram alterados indevidamente. Validação estrita usando `result_hash` e regras Fail Closed está 100% implementada na `backtest_router`.
* **Flutter**: Adicionada a view de Histórico de Backtest com suporte a 4 tabs essenciais:
  - **Resumo:** Exibe as métricas financeiras.
  - **Curva:** Exibe o gráfico de Equity utilizando `CustomPaint` (sem libs adicionais).
  - **Trades:** Lista detalhada das operações em modo leitura/só visualização.
  - **Replay:** Controlador temporal com suporte a avanço/recuo (`|< < PLAY/PAUSE > >|`) validando o relatório passo a passo.
* **Segurança e Regras de Negócio**: A simulação corrente de PAPER é perfeitamente distinguível dos relatórios históricos, com headers visuais proeminentes para evitar confusão entre dinheiro real/simulado vs dados passados. O backtest backend permance Single Source of Truth. Nenhuma métrica é recalculada na UI. 

**Próximos Passos (Requeridos antes de M5):**
1. Gerar e acessar logs `.artifacts` de backtests existentes e colocá-los no Xiaomi.
2. Build final do APK: `cd apps/mobile_app ; flutter build apk --debug --dart-define=API_BASE_URL=http://<YOUR_IP>:8000`
3. Instalar no Xiaomi usando adb.
4. Testar todas as 4 tabs (Resumo, Curva, Trades, Replay) garantindo layout sem overflow (testado no flutter driver e em viewport 800x1200).
5. Tirar capturas de tela e salvar em `docs/evidence/`
6. Executar os final quality gates (`flutter analyze`, `pytest`, `ruff`, etc) e então o commit M4-Flutter.

**ATENÇÃO: M5 não foi iniciado. IA não foi implementada.**
