import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/app.dart';
import 'package:mobile_app/src/live_paper/controller.dart';
import 'package:mobile_app/src/live_paper/mocks.dart';
import 'package:mobile_app/src/live_paper/models.dart';
import 'package:mobile_app/src/live_paper/page.dart';
import 'package:mobile_app/src/shell/app_shell.dart';

Future<LivePaperController> pumpDashboard(
  WidgetTester tester, {
  required MockLivePaperApi api,
  Size size = const Size(1280, 800),
  double textScale = 1.0,
  bool mockPreview = true,
  AppDestination destination = AppDestination.summary,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

  final controller = LivePaperController(
    api: api,
    autoStart: false,
    refreshInterval: const Duration(hours: 1),
  );
  await controller.refresh();
  await tester.pumpWidget(
    TradingBotApp(
      livePaperController: controller,
      useMockLivePaper: true,
      mockPreview: mockPreview,
      initialDestination: destination,
    ),
  );
  await tester.pumpAndSettle();
  return controller;
}

void main() {
  test('dashboard JSON contract parses monetary strings', () {
    final dash = LivePaperDashboard.fromJson({
      'schema_version': '1.0',
      'mode': 'ALPACA_PAPER',
      'simulated_money': true,
      'broker': {
        'name': 'alpaca',
        'connected': true,
        'last_sync_utc': '2026-09-04T17:00:00Z',
        'degraded_reason': null,
      },
      'market': {
        'status': 'OPEN',
        'provider': 'alpaca',
        'feed': 'iex',
        'last_bar_utc': '2026-09-04T16:55:00Z',
        'operational_timeframe': '15m',
      },
      'account': {
        'currency': 'USD',
        'equity': '100324.21',
        'cash': '97401.33',
        'buying_power': '97401.33',
        'day_pnl': '24.81',
        'total_pnl': '324.21',
      },
      'risk': {'paused': false, 'degraded': false, 'reason': null},
      'latest_decision': {
        'symbol': 'AAPL',
        'timeframe': '15m',
        'signal': 'BUY',
        'risk': 'APPROVED',
        'reason': 'baseline strategy',
        'created_at': '2026-09-04T16:58:00Z',
      },
      'positions': [
        {
          'symbol': 'TSLA',
          'qty': '3',
          'avg_entry_price': '305.18',
          'market_value': '920.00',
          'unrealized_pnl': '4.46',
          'unrealized_pnl_pct': '0.48',
        },
      ],
      'updated_at': '2026-09-04T17:00:00Z',
    });
    expect(dash.mode, LivePaperMode.alpacaPaper);
    expect(dash.simulatedMoney, isTrue);
    expect(dash.account.equity, '100324.21');
    expect(dash.positions.first.qty, '3');
  });

  testWidgets('ALPACA PAPER badge and DINHEIRO FICTÍCIO', (tester) async {
    await pumpDashboard(tester, api: MockLivePaperApi());
    expect(find.text('ALPACA PAPER'), findsOneWidget);
    expect(find.text('DINHEIRO FICTÍCIO'), findsOneWidget);
    expect(find.text('MOCK / DESIGN PREVIEW'), findsOneWidget);
  });

  testWidgets('market OPEN CLOSED DEGRADED', (tester) async {
    for (final status in [
      MarketStatus.open,
      MarketStatus.closed,
      MarketStatus.degraded,
    ]) {
      await pumpDashboard(
        tester,
        api: MockLivePaperApi(dashboard: demoDashboard(market: status)),
      );
      expect(find.byKey(const Key('market-status')), findsOneWidget);
      expect(find.text(status.name.toUpperCase() == 'OPEN'
          ? 'OPEN'
          : status.name.toUpperCase() == 'CLOSED'
          ? 'CLOSED'
          : 'DEGRADED'), findsWidgets);
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('broker connected and offline', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(brokerConnected: true)),
    );
    expect(find.text('conectado'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(brokerConnected: false)),
    );
    expect(find.text('broker offline'), findsOneWidget);
    expect(find.textContaining('BROKER OFFLINE'), findsOneWidget);
  });

  testWidgets('risk NORMAL PAUSED DEGRADED', (tester) async {
    await pumpDashboard(tester, api: MockLivePaperApi());
    expect(find.text('NORMAL'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(riskPaused: true)),
    );
    expect(find.text('PAUSED'), findsOneWidget);
    expect(find.text('NOVAS ORDENS BLOQUEADAS'), findsWidgets);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(riskDegraded: true)),
    );
    expect(find.text('DEGRADED'), findsWidgets);
    expect(find.text('EXECUÇÃO BLOQUEADA'), findsWidgets);
  });

  testWidgets('positive negative null P&L', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(dayPnl: '24.81')),
    );
    expect(find.byKey(const Key('day-pnl')), findsOneWidget);
    expect(find.textContaining('+\$24.81'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(dayPnl: '-12.50')),
    );
    expect(find.textContaining('-\$12.50'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(dayPnl: null)),
    );
    expect(find.textContaining('— dia'), findsOneWidget);
  });

  testWidgets('positions empty and filled', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(dashboard: demoDashboard(positions: const [])),
    );
    expect(find.text('Nenhuma posição aberta'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(tester, api: MockLivePaperApi());
    expect(find.text('TSLA'), findsOneWidget);
    expect(find.textContaining('+\$4.46'), findsOneWidget);
  });

  testWidgets('orders empty FILLED PARTIAL REJECTED', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(orders: const []),
    );
    expect(find.text('Nenhuma ordem recente'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(tester, api: MockLivePaperApi());
    expect(find.byKey(const Key('order-status-FILLED')), findsOneWidget);
    expect(find.byKey(const Key('order-status-PARTIAL')), findsOneWidget);
    expect(find.byKey(const Key('order-status-REJECTED')), findsOneWidget);
  });

  testWidgets('latest decision BUY SELL HOLD REJECTED', (tester) async {
    for (final signal in ['BUY', 'SELL', 'HOLD']) {
      await pumpDashboard(
        tester,
        api: MockLivePaperApi(
          dashboard: demoDashboard(
            decision: LiveLatestDecision(
              symbol: 'AAPL',
              timeframe: '15m',
              signal: signal,
              risk: signal == 'HOLD' ? 'HOLD' : 'APPROVED',
              createdAt: DateTime.now().toUtc(),
            ),
          ),
        ),
      );
      expect(find.textContaining(signal), findsWidgets);
      expect(find.textContaining('não é recomendação'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    }

    await pumpDashboard(
      tester,
      api: MockLivePaperApi(
        dashboard: demoDashboard(
          decision: LiveLatestDecision(
            symbol: 'AAPL',
            timeframe: '15m',
            signal: 'BUY',
            risk: 'REJECTED',
            createdAt: DateTime.now().toUtc(),
          ),
        ),
      ),
    );
    expect(find.textContaining('REJECTED'), findsWidgets);
    expect(find.textContaining('bloqueado'), findsOneWidget);
  });

  testWidgets('timeframe selectors keep operational 15m', (tester) async {
    final api = MockLivePaperApi();
    final controller = await pumpDashboard(tester, api: api);
    expect(controller.chartTimeframe, ChartTimeframe.m15);
    expect(controller.operationalTimeframe, '15m');
    expect(find.textContaining('15m · STRATEGY'), findsOneWidget);

    await tester.tap(find.byKey(const Key('tf-5m')));
    await tester.pumpAndSettle();
    expect(controller.chartTimeframe, ChartTimeframe.m5);
    expect(controller.operationalTimeframe, '15m');
    expect(api.lastCandleTimeframe, ChartTimeframe.m5);

    await tester.tap(find.byKey(const Key('tf-1h')));
    await tester.pumpAndSettle();
    expect(controller.chartTimeframe, ChartTimeframe.h1);
    expect(controller.operationalTimeframe, '15m');
  });

  testWidgets('observer OK and DEGRADED', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(observer: demoObserverOk()),
    );
    expect(find.textContaining('Status: OK'), findsOneWidget);
    expect(find.textContaining('SEM AUTORIDADE DE EXECUÇÃO'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(observer: demoObserverDegraded()),
    );
    expect(find.byKey(const Key('observer-degraded-label')), findsOneWidget);
  });

  testWidgets('loading and API error', (tester) async {
    final api = MockLivePaperApi(failDashboard: true);
    final controller = LivePaperController(
      api: api,
      autoStart: false,
      refreshInterval: const Duration(hours: 1),
    );
    await tester.pumpWidget(
      MaterialApp(home: LivePaperPage(controller: controller)),
    );
    await tester.pump();
    // Initial state before refresh is loading with null dashboard.
    expect(find.byKey(const Key('live-paper-loading')), findsOneWidget);
    await controller.refresh();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('live-paper-error')), findsOneWidget);
    expect(find.text('API error'), findsWidgets);
  });

  testWidgets('offline state', (tester) async {
    final api = MockLivePaperApi(offline: true);
    final controller = LivePaperController(
      api: api,
      autoStart: false,
      refreshInterval: const Duration(hours: 1),
    );
    await controller.refresh();
    await tester.pumpWidget(
      MaterialApp(home: LivePaperPage(controller: controller)),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('live-paper-offline')), findsOneWidget);
  });

  for (final size in [
    const Size(1280, 800), // tablet landscape
    const Size(800, 1280), // tablet portrait
    const Size(390, 844), // phone
  ]) {
    for (final scale in [1.0, 1.3, 2.0]) {
      testWidgets('layout $size scale $scale no overflow', (tester) async {
        await pumpDashboard(
          tester,
          api: MockLivePaperApi(),
          size: size,
          textScale: scale,
        );
        expect(tester.takeException(), isNull);
        expect(find.text('ALPACA PAPER'), findsOneWidget);
        expect(find.byKey(const Key('equity-value')), findsOneWidget);
        // Scroll to bottom panels to force layout of remaining content.
        final scrollable = find.byType(Scrollable).first;
        await tester.drag(scrollable, const Offset(0, -800));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.textContaining('SEM AUTORIDADE'), findsWidgets);
      });
    }
  }

  testWidgets('navigation rail on landscape tablet', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(),
      size: const Size(1280, 800),
    );
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('bottom navigation on phone', (tester) async {
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(),
      size: const Size(390, 844),
    );
    expect(find.text('Resumo'), findsWidgets);
    expect(find.text('Mercado'), findsWidgets);
    expect(find.byType(NavigationRail), findsNothing);
  });

  testWidgets('stale market data banner', (tester) async {
    final stale = DateTime.now().toUtc().subtract(const Duration(hours: 2));
    await pumpDashboard(
      tester,
      api: MockLivePaperApi(
        dashboard: demoDashboard(lastBarUtc: stale.toIso8601String()),
      ),
    );
    expect(find.byKey(const Key('stale-market')), findsOneWidget);
    expect(find.text('DADOS ATRASADOS'), findsWidgets);
  });
}
