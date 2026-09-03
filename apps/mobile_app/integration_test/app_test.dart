import 'package:mobile_app/src/market/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mobile_app/src/app.dart';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/controller.dart';

Future<void> waitFor(
  WidgetTester tester,
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final end = DateTime.now().add(timeout);
  while (!condition() && DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 100));
  }
  expect(condition(), isTrue, reason: 'Condição real não atingida em $timeout');
  expect(tester.takeException(), isNull);
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const base = String.fromEnvironment('API_BASE_URL');
  const capture = bool.fromEnvironment('CAPTURE_SCREENSHOTS');
  const reconnect = bool.fromEnvironment('RUN_RECONNECT_TEST');

  for (final orientation in [
    DeviceOrientation.portraitUp,
    DeviceOrientation.landscapeLeft,
  ]) {
    testWidgets('tablet REST + WS + inspeção: $orientation', (tester) async {
      final controller = MarketController(api: HttpMarketApi(base));
      addTearDown(() async {
        controller.dispose();
        await SystemChrome.setPreferredOrientations([]);
      });
      await SystemChrome.setPreferredOrientations([orientation]);
      await tester.pumpWidget(TradingBotApp(controller: controller));
      await waitFor(
        tester,
        () =>
            controller.state == MarketConnectionState.connected &&
            controller.candles.isNotEmpty,
      );
      expect(
        tester.view.physicalSize.width > tester.view.physicalSize.height,
        orientation == DeviceOrientation.landscapeLeft,
      );
      expect(
        controller.marketData?.provider,
        'simulator',
        reason: 'Este teste exige o simulador; não valida streaming Alpaca.',
      );
      final initial = controller.cursor;
      await waitFor(
        tester,
        () => controller.liveEvents > 0 && controller.cursor > initial,
      );
      expect(
        controller.candles.map((c) => c.id).toSet().length,
        controller.candles.length,
      );
      final previous = find.byKey(const Key('previous-candle'));
      await tester.scrollUntilVisible(previous, 100);
      await tester.pump();
      expect(tester.getSize(previous).height, greaterThanOrEqualTo(48));
      await tester.tap(previous);
      await tester.pump();
      expect(find.text('Candle #${controller.cursor - 1}'), findsOneWidget);
      expect(tester.takeException(), isNull);
      debugPrint(
        'M15_SIMULATOR_TABLET_PASS orientation=$orientation REST=${controller.candles.length} WS=${controller.liveEvents} cursor=${controller.cursor}',
      );
      if (capture) {
        await tester.scrollUntilVisible(find.text('TRADING BOT'), -200);
        await tester.pump(const Duration(seconds: 1));
        await binding.convertFlutterSurfaceToImage();
        await tester.pump(const Duration(milliseconds: 500));
        await binding.takeScreenshot(
          orientation == DeviceOrientation.portraitUp
              ? 'm1-tablet-integration-portrait'
              : 'm1-tablet-integration-landscape',
        );
      }
    });
  }
  if (reconnect) {
    testWidgets(
      'tablet recupera lacuna após parada real do backend',
      (tester) async {
        final controller = MarketController(api: HttpMarketApi(base));
        addTearDown(controller.dispose);
        await tester.pumpWidget(TradingBotApp(controller: controller));
        await waitFor(
          tester,
          () => controller.state == MarketConnectionState.connected,
        );
        final originalCursor = controller.cursor;
        debugPrint('M1_RECONNECT_READY cursor=$originalCursor');
        await waitFor(
          tester,
          () => controller.state == MarketConnectionState.offline,
          timeout: const Duration(seconds: 120),
        );
        expect(controller.candles, isNotEmpty);
        debugPrint('M1_OFFLINE_OBSERVED cursor=${controller.cursor}');
        if (capture) {
          await binding.convertFlutterSurfaceToImage();
          await tester.pump(const Duration(milliseconds: 500));
          await binding.takeScreenshot('m1-tablet-offline');
        }
        await waitFor(
          tester,
          () =>
              controller.state == MarketConnectionState.connected &&
              controller.successfulConnections >= 2 &&
              controller.recoveredCandles > 0 &&
              controller.cursor > originalCursor,
          timeout: const Duration(seconds: 120),
        );
        expect(
          controller.candles.map((c) => c.id).toSet().length,
          controller.candles.length,
        );
        expect(
          controller.candles.map((c) => c.openTime).toSet().length,
          controller.candles.length,
        );
        for (var i = 1; i < controller.candles.length; i++) {
          expect(
            controller.candles[i].sequence,
            controller.candles[i - 1].sequence + 1,
          );
        }
        debugPrint(
          'M1_RECONNECT_PASS recovered=${controller.recoveredCandles} cursor=${controller.cursor} connections=${controller.successfulConnections}',
        );
        if (capture) {
          await tester.pump(const Duration(milliseconds: 500));
          await binding.takeScreenshot('m1-tablet-recovered');
        }
      },
      timeout: const Timeout(Duration(minutes: 5)),
    );
  }
}
