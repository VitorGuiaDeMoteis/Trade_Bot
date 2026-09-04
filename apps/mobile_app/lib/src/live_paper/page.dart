import 'package:flutter/material.dart';

import 'controller.dart';
import 'format.dart';
import 'models.dart';
import 'widgets/chart_panel.dart';
import 'widgets/mode_banner.dart';
import 'widgets/panels.dart';

class LivePaperPage extends StatelessWidget {
  const LivePaperPage({
    super.key,
    required this.controller,
    this.onOpenObserver,
    this.mockPreview = false,
  });

  final LivePaperController controller;
  final VoidCallback? onOpenObserver;
  final bool mockPreview;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final state = controller.loadState;
        if (state == LivePaperLoadState.loading &&
            controller.dashboard == null) {
          return const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(key: Key('live-paper-loading')),
                SizedBox(height: 12),
                Text('Carregando live paper…'),
              ],
            ),
          );
        }
        if (state == LivePaperLoadState.offline &&
            controller.dashboard == null) {
          return _StatusBody(
            keyName: 'live-paper-offline',
            icon: Icons.wifi_off,
            title: 'Offline',
            message: controller.errorMessage ?? 'Sem conexão com a API.',
            onRetry: controller.refresh,
          );
        }
        if (state == LivePaperLoadState.error &&
            controller.dashboard == null) {
          return _StatusBody(
            keyName: 'live-paper-error',
            icon: Icons.error_outline,
            title: 'API error',
            message: controller.errorMessage ?? 'Falha ao carregar dashboard.',
            onRetry: controller.refresh,
          );
        }

        final dash = controller.dashboard!;
        final stale = dash.market.isStale();
        return RefreshIndicator(
          onRefresh: controller.refresh,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 900;
              final landscape = constraints.maxWidth > constraints.maxHeight;
              return CustomScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  SliverToBoxAdapter(
                    child: ModeBanner(
                      mode: dash.mode,
                      simulatedMoney: dash.simulatedMoney,
                      marketStatus: dash.market.status,
                      brokerConnected: dash.broker.connected,
                      updatedAt: dash.updatedAt,
                      stale: stale,
                      mockPreview: mockPreview,
                    ),
                  ),
                  if (!dash.broker.connected ||
                      dash.market.status == MarketStatus.degraded ||
                      dash.risk.level != RiskLevel.normal ||
                      stale)
                    SliverToBoxAdapter(
                      child: _AlertsStrip(dashboard: dash, stale: stale),
                    ),
                  SliverPadding(
                    padding: const EdgeInsets.all(12),
                    sliver: SliverToBoxAdapter(
                      child: wide || landscape
                          ? _LandscapeBody(
                              controller: controller,
                              dashboard: dash,
                              onOpenObserver: onOpenObserver,
                            )
                          : _PortraitBody(
                              controller: controller,
                              dashboard: dash,
                              onOpenObserver: onOpenObserver,
                            ),
                    ),
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }
}

class _AlertsStrip extends StatelessWidget {
  const _AlertsStrip({required this.dashboard, required this.stale});
  final LivePaperDashboard dashboard;
  final bool stale;

  @override
  Widget build(BuildContext context) {
    final items = <String>[];
    if (!dashboard.broker.connected) items.add('BROKER OFFLINE');
    if (dashboard.market.status == MarketStatus.closed) {
      items.add('MARKET CLOSED');
    }
    if (dashboard.market.status == MarketStatus.degraded) {
      items.add('MARKET DEGRADED');
    }
    if (stale) items.add('DADOS ATRASADOS');
    if (dashboard.risk.paused) items.add('NOVAS ORDENS BLOQUEADAS');
    if (dashboard.risk.degraded) items.add('EXECUÇÃO BLOQUEADA');
    if (items.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      color: const Color(0xFF3A2A12),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Text(
        items.join('  ·  '),
        key: const Key('alerts-strip'),
        style: const TextStyle(
          color: Color(0xFFE6A23C),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _LandscapeBody extends StatelessWidget {
  const _LandscapeBody({
    required this.controller,
    required this.dashboard,
    this.onOpenObserver,
  });

  final LivePaperController controller;
  final LivePaperDashboard dashboard;
  final VoidCallback? onOpenObserver;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 260,
              child: AccountPanel(account: dashboard.account),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: ChartPanel(
                symbol: controller.chartSymbol,
                operationalTimeframe: controller.operationalTimeframe,
                selectedTimeframe: controller.chartTimeframe,
                onTimeframeSelected: controller.setChartTimeframe,
                candles: controller.candles,
                loading: controller.loadState == LivePaperLoadState.loading,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 260, child: RiskPanel(risk: dashboard.risk)),
            const SizedBox(width: 12),
            Expanded(
              child: DecisionPanel(decision: dashboard.latestDecision),
            ),
          ],
        ),
        const SizedBox(height: 12),
        PositionsPanel(positions: dashboard.positions),
        const SizedBox(height: 12),
        OrdersPanel(orders: controller.orders, compact: true),
        const SizedBox(height: 12),
        ObserverSummaryCard(
          summary: controller.observer,
          onOpen: onOpenObserver,
        ),
        const SizedBox(height: 8),
        Text(
          'provider ${dashboard.market.provider ?? '—'} · feed ${dashboard.market.feed ?? '—'} · last bar ${clockLabel(dashboard.market.lastBarUtc)}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class _PortraitBody extends StatelessWidget {
  const _PortraitBody({
    required this.controller,
    required this.dashboard,
    this.onOpenObserver,
  });

  final LivePaperController controller;
  final LivePaperDashboard dashboard;
  final VoidCallback? onOpenObserver;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AccountPanel(account: dashboard.account),
        const SizedBox(height: 12),
        ChartPanel(
          symbol: controller.chartSymbol,
          operationalTimeframe: controller.operationalTimeframe,
          selectedTimeframe: controller.chartTimeframe,
          onTimeframeSelected: controller.setChartTimeframe,
          candles: controller.candles,
          loading: controller.loadState == LivePaperLoadState.loading,
        ),
        const SizedBox(height: 12),
        RiskPanel(risk: dashboard.risk),
        const SizedBox(height: 12),
        DecisionPanel(decision: dashboard.latestDecision),
        const SizedBox(height: 12),
        PositionsPanel(positions: dashboard.positions),
        const SizedBox(height: 12),
        OrdersPanel(orders: controller.orders, compact: true),
        const SizedBox(height: 12),
        ObserverSummaryCard(
          summary: controller.observer,
          onOpen: onOpenObserver,
        ),
        const SizedBox(height: 8),
        Text(
          'provider ${dashboard.market.provider ?? '—'} · feed ${dashboard.market.feed ?? '—'} · last bar ${clockLabel(dashboard.market.lastBarUtc)}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class LiveOrdersPage extends StatelessWidget {
  const LiveOrdersPage({super.key, required this.controller});

  final LivePaperController controller;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'ORDENS LIVE PAPER',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 4),
            const Text('Somente observação. Sem envio manual de ordens.'),
            const SizedBox(height: 16),
            OrdersPanel(orders: controller.orders),
          ],
        );
      },
    );
  }
}

class _StatusBody extends StatelessWidget {
  const _StatusBody({
    required this.keyName,
    required this.icon,
    required this.title,
    required this.message,
    required this.onRetry,
  });

  final String keyName;
  final IconData icon;
  final String title;
  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, key: Key(keyName)),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }
}
