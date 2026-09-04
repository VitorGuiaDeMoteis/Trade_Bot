import 'package:flutter/material.dart';

import '../backtest/page.dart';
import '../decisions/controller.dart';
import '../decisions/page.dart';
import '../live_paper/controller.dart';
import '../live_paper/mocks.dart';
import '../live_paper/api.dart';
import '../live_paper/page.dart';
import '../market/controller.dart';
import '../market/page.dart';
import '../observer/api.dart';
import '../observer/controller.dart';
import '../observer/page.dart';
import '../paper/page.dart';

enum AppDestination {
  summary,
  market,
  decisions,
  orders,
  backtest,
  system,
}

class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    this.livePaperController,
    this.marketController,
    this.decisionsController,
    this.useMockLivePaper = false,
    this.mockPreview = false,
    this.initialDestination = AppDestination.summary,
  });

  final LivePaperController? livePaperController;
  final MarketController? marketController;
  final DecisionsController? decisionsController;
  final bool useMockLivePaper;
  final bool mockPreview;
  final AppDestination initialDestination;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late AppDestination destination;
  late final LivePaperController livePaper;
  late final bool ownsLivePaper;

  @override
  void initState() {
    super.initState();
    destination = widget.initialDestination;
    ownsLivePaper = widget.livePaperController == null;
    final baseUrl = const String.fromEnvironment('API_BASE_URL');
    final useMock =
        widget.useMockLivePaper ||
        baseUrl.isEmpty ||
        const bool.fromEnvironment('USE_LIVE_PAPER_MOCK', defaultValue: false);
    livePaper =
        widget.livePaperController ??
        LivePaperController(
          api: useMock
              ? MockLivePaperApi(includeDemoMarkers: true)
              : HttpLivePaperApi(baseUrl),
        );
  }

  @override
  void dispose() {
    if (ownsLivePaper) livePaper.dispose();
    super.dispose();
  }

  void _openObserver() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ObserverPage(
          controller: ObserverController(
            api: HttpObserverApi(
              const String.fromEnvironment('API_BASE_URL'),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final useRail = constraints.maxWidth >= 900;
        final body = switch (destination) {
          AppDestination.summary => LivePaperPage(
            controller: livePaper,
            onOpenObserver: _openObserver,
            mockPreview: widget.mockPreview ||
                livePaper.api is MockLivePaperApi,
          ),
          AppDestination.market => MarketPage(
            controller: widget.marketController,
            decisionsController: widget.decisionsController,
          ),
          AppDestination.decisions => DecisionsPage(
            controller: widget.decisionsController,
          ),
          AppDestination.orders => LiveOrdersPage(controller: livePaper),
          AppDestination.backtest => const BacktestPage(),
          AppDestination.system => _SystemPage(
            onOpenObserver: _openObserver,
            onOpenLocalPaper: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const PaperPage(),
                ),
              );
            },
          ),
        };

        if (useRail) {
          return Scaffold(
            body: SafeArea(
              child: Row(
                children: [
                  NavigationRail(
                    selectedIndex: destination.index,
                    onDestinationSelected: (i) => setState(
                      () => destination = AppDestination.values[i],
                    ),
                    labelType: NavigationRailLabelType.all,
                    destinations: const [
                      NavigationRailDestination(
                        icon: Icon(Icons.dashboard_outlined),
                        selectedIcon: Icon(Icons.dashboard),
                        label: Text('Resumo'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.show_chart_outlined),
                        selectedIcon: Icon(Icons.show_chart),
                        label: Text('Mercado'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.account_tree_outlined),
                        selectedIcon: Icon(Icons.account_tree),
                        label: Text('Decisões'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.receipt_long_outlined),
                        selectedIcon: Icon(Icons.receipt_long),
                        label: Text('Ordens'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.history_outlined),
                        selectedIcon: Icon(Icons.history),
                        label: Text('Backtest'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.settings_outlined),
                        selectedIcon: Icon(Icons.settings),
                        label: Text('Sistema'),
                      ),
                    ],
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(child: body),
                ],
              ),
            ),
          );
        }

        return Scaffold(
          body: SafeArea(child: body),
          bottomNavigationBar: Material(
            color: Theme.of(context).colorScheme.surfaceContainer,
            child: SafeArea(
              top: false,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                child: Row(
                  children: [
                    for (final item in AppDestination.values)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        child: _NavChip(
                          selected: destination == item,
                          icon: switch (item) {
                            AppDestination.summary => Icons.dashboard_outlined,
                            AppDestination.market => Icons.show_chart_outlined,
                            AppDestination.decisions =>
                              Icons.account_tree_outlined,
                            AppDestination.orders =>
                              Icons.receipt_long_outlined,
                            AppDestination.backtest => Icons.history_outlined,
                            AppDestination.system => Icons.settings_outlined,
                          },
                          label: switch (item) {
                            AppDestination.summary => 'Resumo',
                            AppDestination.market => 'Mercado',
                            AppDestination.decisions => 'Decisões',
                            AppDestination.orders => 'Ordens',
                            AppDestination.backtest => 'Backtest',
                            AppDestination.system => 'Sistema',
                          },
                          onTap: () => setState(() => destination = item),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _NavChip extends StatelessWidget {
  const _NavChip({
    required this.selected,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minWidth: 72, minHeight: 48),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                color: selected ? colors.primary : colors.onSurfaceVariant,
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? colors.primary : colors.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SystemPage extends StatelessWidget {
  const _SystemPage({
    required this.onOpenObserver,
    required this.onOpenLocalPaper,
  });

  final VoidCallback onOpenObserver;
  final VoidCallback onOpenLocalPaper;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text('SISTEMA', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'Modos distintos: ALPACA PAPER · LOCAL PAPER · BACKTEST · AI OBSERVER',
        ),
        const SizedBox(height: 20),
        ListTile(
          leading: const Icon(Icons.psychology),
          title: const Text('AI Observer'),
          subtitle: const Text('OBSERVADOR · SEM AUTORIDADE DE EXECUÇÃO'),
          onTap: onOpenObserver,
        ),
        ListTile(
          leading: const Icon(Icons.account_balance_wallet_outlined),
          title: const Text('Local Paper'),
          subtitle: const Text('Carteira simulada local (não Alpaca)'),
          onTap: onOpenLocalPaper,
        ),
      ],
    );
  }
}
