import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/app.dart';
import 'package:mobile_app/src/shell/app_shell.dart';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/controller.dart';
import 'package:mobile_app/src/market/models.dart';
import 'support/market_fake.dart';

void main() {
  for (final size in [
    const Size(320, 568),
    const Size(390, 844),
    const Size(844, 390),
    const Size(800, 1280),
    const Size(1280, 800),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        'histórico, inspeção, atualização e layout $size texto $scale',
        (tester) async {
          tester.view.devicePixelRatio = 1;
          tester.view.physicalSize = size;
          tester.platformDispatcher.textScaleFactorTestValue = scale;
          addTearDown(tester.view.resetPhysicalSize);
          addTearDown(tester.view.resetDevicePixelRatio);
          addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
          final api = FakeApi();
          final controller = MarketController(api: api);
          await tester.pumpWidget(TradingBotApp(controller: controller, initialDestination: AppDestination.market, useMockLivePaper: true));
          await tester.pump();
          expect(find.text('SIMULADO'), findsOneWidget);
          expect(find.text('Conectado'), findsOneWidget);
          final marketScroll = find.descendant(
            of: find.byType(ListView),
            matching: find.byType(Scrollable),
          ).first;
          await tester.scrollUntilVisible(
            find.byKey(const Key('candle-count')),
            120,
            scrollable: marketScroll,
          );
          expect(find.text('3 candles carregados para TEST'), findsOneWidget);
          final previous = find.byKey(const Key('previous-candle'));
          await tester.scrollUntilVisible(previous, 150, scrollable: marketScroll);
          await tester.pump();
          expect(tester.getSize(previous).height, greaterThanOrEqualTo(48));
          expect(tester.getSize(previous).width, greaterThanOrEqualTo(48));
          await tester.tap(previous);
          await tester.pump();
          expect(find.text('Candle #2'), findsOneWidget);
          api.sockets.last.add(eventJson(4));
          await tester.pump();
          expect(controller.candles.length, 4);
          expect(find.text('Candle #2'), findsOneWidget);
          final chart = find.byKey(const Key('candle-chart'));
          await tester.ensureVisible(chart);
          await tester.pump();
          await tester.tapAt(tester.getTopLeft(chart) + const Offset(8, 50));
          await tester.pump();
          expect(find.text('Candle #1'), findsOneWidget);
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox());
          controller.dispose();
        },
      );
    }
  }
  testWidgets('acessibilidade: contraste, labels e alvos de toque', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 1200);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final semantics = tester.ensureSemantics();
    final controller = MarketController(api: FakeApi());
    try {
      await tester.pumpWidget(TradingBotApp(controller: controller, initialDestination: AppDestination.market, useMockLivePaper: true));
      await tester.pump();
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    } finally {
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    }
  });
  testWidgets('carregamento inicial e estado vazio', (tester) async {
    final pending = Completer<Snapshot>();
    final api = FakeApi()..responses.add(() => pending.future);
    final controller = MarketController(api: api);
    await tester.pumpWidget(TradingBotApp(controller: controller, initialDestination: AppDestination.market, useMockLivePaper: true));
    expect(find.text('Carregando'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    pending.complete(Snapshot.fromJson(snapshotJson([])));
    await tester.pump();
    expect(find.textContaining('Nenhum candle carregado'), findsOneWidget);
    expect(find.byKey(const Key('candle-chart')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });
  testWidgets('offline, backoff, paginação da lacuna e deduplicação', (
    tester,
  ) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    api.sockets.last.add(eventJson(4));
    api.sockets.last.add(eventJson(4));
    await tester.pump();
    expect(controller.candles.length, 4);
    expect(controller.liveEvents, 1);
    api.responses.addAll([
      () async => throw const ApiFailure(FailureKind.offline),
      () async => Snapshot.fromJson(snapshotJson([5, 6], high: 8)),
      () async => Snapshot.fromJson(snapshotJson([7, 8], high: 8)),
    ]);
    unawaited(api.sockets.last.close());
    await tester.pump();
    expect(controller.state, MarketConnectionState.offline);
    expect(controller.candles.length, 4);
    await tester.pump(const Duration(milliseconds: 999));
    expect(api.requests.length, 1);
    await tester.pump(const Duration(milliseconds: 1));
    expect(api.requests.length, 2);
    await tester.pump(const Duration(milliseconds: 1999));
    expect(api.requests.length, 2);
    await tester.pump(const Duration(milliseconds: 1));
    expect(controller.cursor, 8);
    expect(controller.recoveredCandles, 4);
    expect(controller.candles.map((c) => c.id).toSet().length, 8);
    expect(api.requests.last, (after: 6, through: 8, stream: 'stream-1'));
    expect(api.connectCursors, [3, 8]);
    expect(controller.state, MarketConnectionState.connected);
    controller.dispose();
  });
  testWidgets('lacuna no stream recupera via REST', (tester) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    api.responses.add(() async => Snapshot.fromJson(snapshotJson([4, 5])));
    api.sockets.last.add(eventJson(5));
    await tester.pump();
    expect(controller.state, MarketConnectionState.degraded);
    expect(controller.cursor, 3);
    await tester.pump(const Duration(seconds: 1));
    expect(controller.cursor, 5);
    expect(controller.recoveredCandles, 2);
    controller.dispose();
  });
  testWidgets('stream alterado reinicia snapshot sem misturar históricos', (
    tester,
  ) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    api.responses.addAll([
      () async => throw const ApiFailure(FailureKind.reset),
      () async => Snapshot.fromJson(snapshotJson([1], stream: 'stream-2')),
    ]);
    unawaited(controller.retryNow());
    await tester.pump();
    expect(controller.streamId, 'stream-2');
    expect(controller.candles.length, 1);
    expect(api.requests.last.after, isNull);
    controller.dispose();
  });
  testWidgets('heartbeat e dispose cancelam tentativas', (tester) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    await tester.pump(const Duration(seconds: 8));
    expect(controller.state, MarketConnectionState.offline);
    controller.dispose();
    await tester.pump(const Duration(minutes: 1));
    expect(api.requests.length, 1);
  });
  for (final entry in [
    (FailureKind.offline, 'Offline'),
    (FailureKind.degraded, 'Degradado'),
    (FailureKind.invalid, 'Erro de configuração'),
    (FailureKind.configuration, 'Erro de configuração'),
  ]) {
    testWidgets('estado $entry e recuperação manual', (tester) async {
      final api = FakeApi()
        ..responses.add(() async => throw ApiFailure(entry.$1));
      final controller = MarketController(api: api);
      await tester.pumpWidget(TradingBotApp(controller: controller, initialDestination: AppDestination.market, useMockLivePaper: true));
      await tester.pump();
      expect(find.text(entry.$2), findsOneWidget);
      final button = find.byKey(const Key('retry-button'));
      await tester.ensureVisible(button);
      await tester.pump();
      expect(tester.getSize(button).height, greaterThanOrEqualTo(48));
      await tester.tap(button);
      await tester.pump();
      expect(controller.state, MarketConnectionState.connected);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    });
  }
  testWidgets('simulador parado degrada tela com gráfico preservado', (
    tester,
  ) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await tester.pumpWidget(TradingBotApp(controller: controller, initialDestination: AppDestination.market, useMockLivePaper: true));
    await tester.pump();
    api.sockets.last.add(statusJson(state: 'stopped'));
    await tester.pump();
    expect(find.text('Degradado'), findsOneWidget);
    expect(controller.candles.length, 3);
    api.sockets.last.add(statusJson());
    await tester.pump();
    expect(find.text('Conectado'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });
  testWidgets('dados inválidos não entram no gráfico', (tester) async {
    final api = FakeApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    final event = eventJson(4);
    (event['payload'] as Json)['high'] = '0';
    api.sockets.last.add(event);
    await tester.pump();
    expect(controller.state, MarketConnectionState.configurationError);
    expect(controller.cursor, 3);
    controller.dispose();
  });
}
