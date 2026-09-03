import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'chart.dart';
import 'controller.dart';
import 'models.dart';

class MarketPage extends StatefulWidget {
  const MarketPage({super.key, this.controller});

  final MarketController? controller;

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
              MarketConnectionState.market_closed => 'Mercado Fechado',
              MarketConnectionState.delayed => 'Atrasado',
              MarketConnectionState.degraded => 'Degradado',
              MarketConnectionState.offline => 'Offline',
              MarketConnectionState.configuration_error => 'Erro Config',
            };
            final stateColor = switch (state) {
              MarketConnectionState.connected => Colors.green,
              MarketConnectionState.market_closed => Colors.grey,
              MarketConnectionState.reconnecting => Colors.orange,
              MarketConnectionState.delayed => Colors.yellow,
              MarketConnectionState.degraded => Colors.deepOrange,
              MarketConnectionState.configuration_error => Colors.red,
              _ => null,
            };
            final stateIcon = switch (state) {
              MarketConnectionState.connected => Icons.wifi,
              MarketConnectionState.market_closed => Icons.nightlight_round,
              MarketConnectionState.delayed => Icons.timer,
              MarketConnectionState.reconnecting => Icons.sync,
              _ => Icons.wifi_off,
            };
            final warning = [
              MarketConnectionState.offline,
              MarketConnectionState.degraded,
              MarketConnectionState.configuration_error,
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
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 10,
                      runSpacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        _Badge(
                          label: info?.provider != 'simulator' ? 'DADOS REAIS' : 'SIMULADO',
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
                            label: 'FONTE: ALPACA / ${info?.feed?.toUpperCase() ?? 'IEX'}',
                            icon: Icons.source,
                          ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    if (availableSymbols.isNotEmpty)
                      SegmentedButton<String>(
                        segments: availableSymbols
                            .map((s) => ButtonSegment<String>(
                                  value: s,
                                  label: Text(s),
                                ))
                            .toList(),
                        selected: {controller.selectedSymbol},
                        onSelectionChanged: (Set<String> newSelection) {
                          controller.setSymbol(newSelection.first);
                        },
                      )
                    else
                      Text(
                        '${controller.selectedSymbol} / 1h',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                    const SizedBox(height: 12),
                    Text(
                      info?.provider != 'simulator'
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
                      const Center(child: Text('Buscando histórico simulado…')),
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
                      'M1 · Monitoramento de dados simulados. Sem ordens ou conexão com corretoras.',
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
        children: [Icon(icon, size: 18, color: color), Text(label, style: color != null ? TextStyle(color: color, fontWeight: FontWeight.bold) : null)],
      ),
    ),
  );
}
