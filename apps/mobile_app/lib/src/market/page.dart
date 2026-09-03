import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'chart.dart';
import 'controller.dart';

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
              MarketConnectionState.live => 'Conectado',
              MarketConnectionState.offline => 'Offline',
              MarketConnectionState.degraded => 'Degradado',
              MarketConnectionState.error => 'Erro de conexão',
            };
            final warning = [
              MarketConnectionState.offline,
              MarketConnectionState.degraded,
              MarketConnectionState.error,
            ].contains(state);
            final info = controller.simulator;
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
                        const _Badge(
                          label: 'SIMULADO',
                          icon: Icons.science_outlined,
                        ),
                        Semantics(
                          liveRegion: true,
                          child: _Badge(
                            label: label,
                            icon: state == MarketConnectionState.live
                                ? Icons.wifi
                                : Icons.wifi_off,
                          ),
                        ),
                        if (info != null)
                          _Badge(
                            label: info.accelerated
                                ? 'ACELERADA · 1h a cada ${info.interval.toStringAsFixed(1)} s'
                                : 'NORMAL · 1h a cada hora',
                            icon: Icons.schedule,
                          ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'TEST / 1h',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Ativo fictício · candles fechados · relógio virtual em UTC',
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 16,
                      runSpacing: 4,
                      children: [
                        Text(
                          '${controller.candles.length} candles carregados',
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
                    if (controller.candles.isNotEmpty)
                      CandleChart(candles: controller.candles)
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
  const _Badge({required this.label, required this.icon});
  final String label;
  final IconData icon;

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
        children: [Icon(icon, size: 18), Text(label)],
      ),
    ),
  );
}
