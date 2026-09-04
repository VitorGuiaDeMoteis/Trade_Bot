import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/backtest/api.dart';
import 'package:mobile_app/src/backtest/controller.dart';
import 'package:mobile_app/src/backtest/models.dart';
import 'package:mobile_app/src/backtest/page.dart';

Map<String, dynamic> fixture() =>
    jsonDecode(File('test/fixtures/m4-report.json').readAsStringSync())
        as Map<String, dynamic>;

void main() {
  testWidgets('replay controls stay above Android navigation inset', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(900, 1400);
    tester.view.devicePixelRatio = 1;
    tester.view.padding = const FakeViewPadding(bottom: 48);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPadding);
    final controller = BacktestController(
      api: HttpBacktestApi('http://127.0.0.1:8000'),
    )..currentReport = BacktestReport.fromJson(fixture());
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(home: BacktestDetailPage(controller: controller)),
    );
    await tester.tap(find.text('Replay'));
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.byIcon(Icons.fast_forward)).bottom,
      lessThanOrEqualTo(1352),
    );
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'replay associates OPEN execution with its CLOSE frame, never next frame',
    (tester) async {
      tester.view.physicalSize = const Size(900, 1400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final controller = BacktestController(
        api: HttpBacktestApi('http://127.0.0.1:8000'),
      )..currentReport = BacktestReport.fromJson(fixture());
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        MaterialApp(home: BacktestDetailPage(controller: controller)),
      );
      await tester.tap(find.text('Replay'));
      await tester.pumpAndSettle();
      expect(find.text('Eventos neste candle'), findsNothing);
      await tester.tap(find.byIcon(Icons.fast_forward));
      await tester.pumpAndSettle();
      expect(controller.replayIndex, 1);
      expect(find.textContaining('Price: 100.0000000000'), findsOneWidget);
      expect(find.textContaining('Price: 110.0000000000'), findsNothing);
      await tester.tap(find.byIcon(Icons.skip_next));
      await tester.pumpAndSettle();
      expect(controller.replayIndex, 2);
      expect(find.textContaining('Price: 110.0000000000'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.fast_rewind));
      await tester.pumpAndSettle();
      expect(controller.replayIndex, 1);
      await tester.tap(find.byIcon(Icons.skip_previous));
      await tester.pumpAndSettle();
      expect(controller.replayIndex, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('empty dataset replay remains readable without crash', (
    tester,
  ) async {
    final raw = fixture()..['equity_curve'] = [];
    final controller = BacktestController(
      api: HttpBacktestApi('http://127.0.0.1:8000'),
    )..currentReport = BacktestReport.fromJson(raw);
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(home: BacktestDetailPage(controller: controller)),
    );
    await tester.tap(find.text('Replay'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Nenhum frame neste relatório.'), findsOneWidget);
  });
}
