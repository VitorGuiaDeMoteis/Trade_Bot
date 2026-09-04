import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/live_paper/controller.dart';
import 'package:mobile_app/src/live_paper/mocks.dart';
import 'package:mobile_app/src/live_paper/models.dart';
import 'package:mobile_app/src/shell/app_shell.dart';

/// Golden previews are MOCK / DESIGN PREVIEW — not live Xiaomi/API validation.
/// Update with: flutter test test/live_paper_screenshots_test.dart --update-goldens
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> capture(
    WidgetTester tester, {
    required String name,
    required Size size,
    required MockLivePaperApi api,
    AppDestination destination = AppDestination.summary,
  }) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = LivePaperController(
      api: api,
      autoStart: false,
      refreshInterval: const Duration(hours: 1),
    );
    await controller.refresh();

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          scaffoldBackgroundColor: const Color(0xFF0A0E14),
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF7AA2FF),
            brightness: Brightness.dark,
          ),
        ),
        home: AppShell(
          livePaperController: controller,
          useMockLivePaper: true,
          mockPreview: true,
          initialDestination: destination,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    await expectLater(
      find.byType(AppShell),
      matchesGoldenFile('goldens/live-paper-ui-$name-mock.png'),
    );
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  }

  testWidgets('screenshot summary-landscape', (tester) async {
    await capture(
      tester,
      name: 'summary-landscape',
      size: const Size(1280, 800),
      api: MockLivePaperApi(includeDemoMarkers: true),
    );
  });

  testWidgets('screenshot summary-portrait', (tester) async {
    await capture(
      tester,
      name: 'summary-portrait',
      size: const Size(800, 1280),
      api: MockLivePaperApi(includeDemoMarkers: true),
    );
  });

  testWidgets('screenshot market', (tester) async {
    await capture(
      tester,
      name: 'market',
      size: const Size(1280, 800),
      api: MockLivePaperApi(
        dashboard: demoDashboard(market: MarketStatus.open),
      ),
    );
  });

  testWidgets('screenshot positions', (tester) async {
    await capture(
      tester,
      name: 'positions',
      size: const Size(1280, 800),
      api: MockLivePaperApi(),
    );
  });

  testWidgets('screenshot orders', (tester) async {
    await capture(
      tester,
      name: 'orders',
      size: const Size(1280, 800),
      api: MockLivePaperApi(),
      destination: AppDestination.orders,
    );
  });

  testWidgets('screenshot paused', (tester) async {
    await capture(
      tester,
      name: 'paused',
      size: const Size(1280, 800),
      api: MockLivePaperApi(dashboard: demoDashboard(riskPaused: true)),
    );
  });

  testWidgets('screenshot degraded', (tester) async {
    await capture(
      tester,
      name: 'degraded',
      size: const Size(1280, 800),
      api: MockLivePaperApi(
        dashboard: demoDashboard(
          market: MarketStatus.degraded,
          riskDegraded: true,
          brokerConnected: false,
        ),
        observer: demoObserverDegraded(),
      ),
    );
  });
}
