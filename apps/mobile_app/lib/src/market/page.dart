import '../paper/controller.dart';
import '../paper/page.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import '../decisions/controller.dart';
import '../decisions/page.dart';

import 'api.dart';
import 'chart.dart';
import 'controller.dart';
import 'models.dart';

class MarketPage extends StatefulWidget {
  const MarketPage({super.key, this.controller, this.decisionsController});

  final MarketController? controller;
  final DecisionsController? decisionsController;

  @override
  State<MarketPage> createState() => _MarketPageState();
}

class _MarketPageState extends State<MarketPage> {
  late final MarketController controller;

  @override
  void initState() {
    super.initState();
    controller =
        widget.controller ??
        MarketController(
          api: HttpMarketApi(const String.fromEnvironment('API_BASE_URL')),
        );
    unawaited(controller.start());
  }

  @override
  void dispose() {
    if (widget.controller == null) controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(

      floatingActionButton: FloatingActionButton(
        backgroundColor: Colors.orange, tooltip: 'Carteira Simulada',
        child: const Icon(Icons.account_balance_wallet, color: Colors.white),
        onPressed: () {
          Navigator.push(context, MaterialPageRoute(builder: (_) => PaperPage(controller: PaperController())));
        },
      ),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: controller,
          builder: (context, _) {
            final state = controller.state;
            final colors = Theme.of(context).colorScheme;
            final label = switch (state) {
              MarketConnectionState.loading => 'Carregando',
              MarketConnectionState.connecting => 'Conectando',
              MarketConnectionState.connected => 'Conectado',
              MarketConnectionState.reconnecting => 'Reconectando',
              MarketConnectionState.marketClosed => 'Sessão regular fechada',
              MarketConnectionState.delayed => 'Atrasado',
              MarketConnectionState.degraded => 'Degradado',
              MarketConnectionState.offline => 'Offline',
              MarketConnectionState.configurationError =>
                'Erro de configuração',
            };
            final stateColor = switch (state) {
              MarketConnectionState.connected => Colors.green,
              MarketConnectionState.marketClosed => Colors.grey,
              MarketConnectionState.reconnecting => Colors.orange,
              MarketConnectionState.delayed => Colors.yellow,
              MarketConnectionState.degraded => Colors.deepOrange,
              MarketConnectionState.configurationError => Colors.red,
              _ => null,
            };
            final stateIcon = switch (state) {
              MarketConnectionState.connected => Icons.wifi,
              MarketConnectionState.marketClosed => Icons.nightlight_round,
              MarketConnectionState.delayed => Icons.timer,
              MarketConnectionState.reconnecting => Icons.sync,
              _ => Icons.wifi_off,
            };
            final warning = [
              MarketConnectionState.offline,
              MarketConnectionState.degraded,
              MarketConnectionState.configurationError,
            ].contains(state);
            final info = controller.marketData;
            final availableSymbols = info?.symbols ?? [];
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1200),
                child: ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    Text(
                      'TRADING BOT',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => DecisionsPage(
                              controller: widget.decisionsController,
                            ),
                          ),
                        ),
                        style: TextButton.styleFrom(
                          minimumSize: const Size(48, 48),
                        ),
                        icon: const Icon(Icons.account_tree_outlined),
                        label: const Text('Decisões'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 10,
                      runSpacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        _Badge(
                          label: switch (info?.provider) {
                            'alpaca' => 'DADOS REAIS',
                            'simulator' => 'SIMULADO',
                            _ => 'AGUARDANDO FONTE',
                          },
                          icon: Icons.science_outlined,
                        ),
                        Semantics(
                          liveRegion: true,
                          child: _Badge(
                            label: label,
                            icon: stateIcon,
                            color: stateColor,
                          ),
                        ),
                        if (info?.provider == 'alpaca')
                          _Badge(
                            label:
                                'FONTE: ALPACA / ${info?.feed?.toUpperCase() ?? 'IEX'}',
                            icon: Icons.source,
                          ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    if (availableSymbols.isNotEmpty)
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: availableSymbols
                            .map(
                              (symbol) => ConstrainedBox(
                                constraints: const BoxConstraints(
                                  minWidth: 64,
                                  minHeight: 48,
                                ),
                                child: ChoiceChip(
                                  label: Text(symbol),
                                  materialTapTargetSize:
                                      MaterialTapTargetSize.padded,
                                  selected: controller.selectedSymbol == symbol,
                                  onSelected: (_) =>
                                      controller.setSymbol(symbol),
                                ),
                              ),
                            )
                            .toList(),
                      )
                    else
                      Text(
                        '${controller.selectedSymbol} / 1h',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                    const SizedBox(height: 12),
                    Text('${controller.selectedSymbol} / 1h'),
                    if (info?.accelerated == true)
                      const Text('Simulação acelerada'),
                    Text(
                      info?.provider == 'alpaca'
                          ? 'Ativos reais · candles fechados · relógio em UTC'
                          : 'Ativo fictício · candles fechados · relógio virtual em UTC',
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 16,
                      runSpacing: 4,
                      children: [
                        Text(
                          '${controller.filteredCandles.length} candles carregados para ${controller.selectedSymbol}',
                          key: const Key('candle-count'),
                        ),
                        Text(
                          'Recebido: ${controller.lastUpdatedAt == null ? 'aguardando' : utcLabel(controller.lastUpdatedAt!)}',
                        ),
                      ],
                    ),
                    if (warning) ...[
                      const SizedBox(height: 16),
                      Card(
                        color: colors.surfaceContainerHigh,
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                controller.message ?? 'Aguardando recuperação.',
                              ),
                              const SizedBox(height: 12),
                              FilledButton.icon(
                                key: const Key('retry-button'),
                                onPressed: controller.retryNow,
                                icon: const Icon(Icons.refresh),
                                label: const Text('Tentar novamente'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                    if (state == MarketConnectionState.loading) ...[
                      const SizedBox(height: 24),
                      const Center(child: CircularProgressIndicator()),
                      const SizedBox(height: 12),
                      const Center(child: Text('Buscando histórico…')),
                    ],
                    const SizedBox(height: 16),
                    if (controller.filteredCandles.isNotEmpty)
                      CandleChart(candles: controller.filteredCandles)
                    else if (state != MarketConnectionState.loading)
                      const Card(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: Text(
                            'Nenhum candle carregado. O gráfico aparecerá quando houver dados.',
                          ),
                        ),
                      ),
                    const SizedBox(height: 16),
                    Text(
                      'M1.5 · Análise e decisão simuladas. Nenhuma ordem é criada.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.icon, this.color});
  final String label;
  final IconData icon;
  final Color? color;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(8),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      child: Wrap(
        spacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Icon(icon, size: 18, color: color),
          Text(
            label,
            style: color != null
                ? TextStyle(color: color, fontWeight: FontWeight.bold)
                : null,
          ),
        ],
      ),
    ),
  );
}
