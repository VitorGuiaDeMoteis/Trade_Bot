import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile_app/src/app.dart';
import 'package:mobile_app/src/shell/app_shell.dart';
import 'package:mobile_app/src/decisions/api.dart';
import 'package:mobile_app/src/decisions/controller.dart';
import 'package:mobile_app/src/decisions/models.dart';
import 'package:mobile_app/src/decisions/page.dart';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/controller.dart';
import 'package:mobile_app/src/market/models.dart';
import 'support/market_fake.dart';

Json decisionsJson(String symbol, {bool empty = false}) => {
  'schema_version': '1.0',
  'execution': 'NONE',
  'symbol': symbol,
  'symbols': ['SPY', 'AAPL', 'TSLA'],
  'timeframe': '1h',
  'limit': 50,
  'market_data': {
    'provider': 'alpaca',
    'feed': 'iex',
    'state': 'market_closed',
  },
  'items': empty
      ? []
      : [
          for (final seq in [3, 2, 1])
            {
              'candle': {
                ...candleJson(seq),
                'symbol': symbol,
                'provider': 'alpaca',
                'regime': null,
                'close': seq == 3 ? '101' : (seq == 2 ? '99' : '100'),
              },
              'signal': {
                'signal_id': '$symbol-signal-$seq',
                'candle_id': 'candle-$seq',
                'stream_id': 'stream-1',
                'signal_type': seq == 3 ? 'BUY' : (seq == 2 ? 'SELL' : 'HOLD'),
                'strategy_version': 'v1-deterministic',
                'reason': seq == 3
                    ? 'Fechamento acima da abertura.'
                    : (seq == 2
                          ? 'Fechamento abaixo da abertura.'
                          : 'Abertura e fechamento equivalentes. Sem ação.'),
                'generated_at': '2026-09-03T20:00:00Z',
              },
              'risk': {
                'decision_id': '$symbol-risk-$seq',
                'signal_id': '$symbol-signal-$seq',
                'decision': seq == 2 ? 'REJECTED' : 'APPROVED',
                'reason': seq == 2
                    ? 'Sistema está pausado.'
                    : 'Aprovado pelas regras de risco.',
                'decided_at': '2026-09-03T20:00:00Z',
              },
            },
        ],
};

class FakeDecisions implements DecisionsApi {
  final requests = <String?>[];
  Future<DecisionsSnapshot> Function(String?)? handler;
  @override
  Future<DecisionsSnapshot> fetch({String? symbol}) async {
    requests.add(symbol);
    return handler != null
        ? handler!(symbol)
        : DecisionsSnapshot.fromJson(decisionsJson(symbol ?? 'SPY'));
  }

  @override
  void dispose() {}
}

Future<VoidCallback> openDecisions(
  WidgetTester tester,
  DecisionsController decisions,
) async {
  final market = MarketController(api: FakeApi());
  await tester.pumpWidget(
    TradingBotApp(
      controller: market,
      decisionsController: decisions,
      initialDestination: AppDestination.decisions,
      useMockLivePaper: true,
    ),
  );
  await tester.pumpAndSettle();
  return () {
    market.dispose();
    decisions.dispose();
  };
}

void main() {
  for (final size in [
    const Size(320, 568),
    const Size(390, 844),
    const Size(844, 390),
    const Size(800, 1280),
    const Size(1280, 800),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('timeline and detail $size text $scale', (tester) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = size;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final dispose = await openDecisions(
          tester,
          DecisionsController(api: FakeDecisions()),
        );
        expect(find.text('DECISÕES'), findsOneWidget);
        final timeline = find.descendant(
          of: find.byType(DecisionsPage),
          matching: find.byType(Scrollable),
        );
        await tester.scrollUntilVisible(
          find.byKey(const Key('select-SPY')),
          120,
          scrollable: timeline,
        );
        expect(
          tester.getSize(find.byKey(const Key('select-SPY'))).height,
          greaterThanOrEqualTo(48),
        );
        await tester.scrollUntilVisible(
          find.byKey(const Key('decision-type-SPY-signal-3')),
          160,
          scrollable: timeline,
        );
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('decision-type-SPY-signal-3')));
        await tester.pumpAndSettle();
        expect(find.text('Detalhe da decisão'), findsOneWidget);
        await tester.scrollUntilVisible(find.text('OPEN    100.0000'), 120);
        expect(find.text('OPEN    100.0000'), findsOneWidget);
        await tester.scrollUntilVisible(
          find.text('EXECUÇÃO · NENHUMA ORDEM ENVIADA'),
          180,
        );
        expect(find.text('EXECUÇÃO · NENHUMA ORDEM ENVIADA'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pageBack();
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('HOLD · SEM AÇÃO'),
          160,
          scrollable: timeline,
        );
        expect(
          find.text('SEM AÇÃO · nenhuma operação seria executada.'),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        dispose();
      });
    }
  }
  testWidgets('selection SPY AAPL TSLA, counts and risk reasons', (
    tester,
  ) async {
    final api = FakeDecisions();
    final dispose = await openDecisions(tester, DecisionsController(api: api));
    for (final symbol in ['SPY', 'AAPL', 'TSLA']) {
      final scrollable = find.descendant(
        of: find.byType(DecisionsPage),
        matching: find.byType(Scrollable),
      );
      await tester.scrollUntilVisible(
        find.byKey(Key('select-$symbol')),
        -200,
        scrollable: scrollable,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(Key('select-$symbol')));
      await tester.pumpAndSettle();
      expect(find.text('$symbol · últimas 3 decisões'), findsOneWidget);
      for (final type in ['BUY', 'SELL', 'HOLD']) {
        expect(find.text('$type  1'), findsOneWidget);
      }
      await tester.scrollUntilVisible(
        find.byKey(Key('decision-type-$symbol-signal-2')),
        180,
        scrollable: scrollable,
      );
      expect(find.text('Risco · REJECTED'), findsOneWidget);
      expect(find.text('Sistema está pausado.'), findsOneWidget);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(Key('decision-type-$symbol-signal-2')));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Risco · REJECTED'), 150);
      expect(find.text('Sistema está pausado.'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
    }
    expect(api.requests, [null, 'AAPL', 'TSLA']);
    await tester.pumpWidget(const SizedBox());
    dispose();
  });
  testWidgets('loading empty offline and retry', (tester) async {
    final pending = Completer<DecisionsSnapshot>();
    final api = FakeDecisions()..handler = (_) => pending.future;
    final controller = DecisionsController(api: api);
    await tester.pumpWidget(
      MaterialApp(home: DecisionsPage(controller: controller)),
    );
    await tester.pump();
    expect(find.text('Carregando decisões…'), findsOneWidget);
    pending.complete(
      DecisionsSnapshot.fromJson(decisionsJson('SPY', empty: true)),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Nenhuma decisão persistida para este ativo.'),
      findsOneWidget,
    );
    api.handler = (_) async => throw http.ClientException('offline');
    await controller.refresh();
    await tester.pump();
    expect(
      find.text('Offline. Não foi possível consultar o backend.'),
      findsOneWidget,
    );
    api.handler = null;
    await tester.ensureVisible(find.byKey(const Key('refresh-decisions')));
    await tester.tap(find.byKey(const Key('refresh-decisions')));
    await tester.pumpAndSettle();
    expect(find.text('SPY · últimas 3 decisões'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });
  test(
    'late responses cannot replace newly selected symbol and disposal is safe',
    () async {
      final api = FakeDecisions();
      final controller = DecisionsController(api: api);
      await controller.refresh();
      final pending = Completer<DecisionsSnapshot>();
      api.handler = (symbol) => symbol == 'AAPL'
          ? pending.future
          : Future.value(DecisionsSnapshot.fromJson(decisionsJson(symbol!)));
      final old = controller.select('AAPL');
      await controller.select('TSLA');
      pending.complete(DecisionsSnapshot.fromJson(decisionsJson('AAPL')));
      await old;
      expect(controller.snapshot!.symbol, 'TSLA');
      api.handler = (_) async =>
          DecisionsSnapshot.fromJson(decisionsJson('SPY'));
      await controller.refresh();
      expect(controller.snapshot!.symbol, 'TSLA');
      expect(controller.message, contains('inválida'));
      final delayed = Completer<DecisionsSnapshot>();
      api.handler = (_) => delayed.future;
      final last = controller.refresh();
      controller.dispose();
      delayed.complete(DecisionsSnapshot.fromJson(decisionsJson('TSLA')));
      await last;
    },
  );
  test('API readonly query and exact Decimal strings', () async {
    final api = HttpDecisionsApi(
      'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/decisions');
        expect(request.url.queryParameters, {
          'symbol': 'AAPL',
          'timeframe': '1h',
          'limit': '50',
        });
        return http.Response(jsonEncode(decisionsJson('AAPL')), 200);
      }),
    );
    final result = await api.fetch(symbol: 'AAPL');
    expect(result.items.first.candle.open, '100.0000');
    api.dispose();
  });
  for (final status in [503, 422]) {
    test('API failure $status never becomes empty history', () async {
      final api = HttpDecisionsApi(
        'http://localhost',
        client: MockClient((_) async => http.Response('{}', status)),
      );
      await expectLater(api.fetch(), throwsA(isA<ApiFailure>()));
      api.dispose();
    });
  }
  test('invalid contract graph and execution rejected', () {
    for (final field in ['execution', 'schema_version']) {
      final json = decisionsJson('SPY')..[field] = 'invalid';
      expect(() => DecisionsSnapshot.fromJson(json), throwsFormatException);
    }
    final graph = decisionsJson('SPY');
    graph['items'][0]['risk']['signal_id'] = 'different';
    expect(() => DecisionsSnapshot.fromJson(graph), throwsFormatException);
    final mixed = decisionsJson('SPY');
    mixed['items'][0]['candle']['symbol'] = 'AAPL';
    expect(() => DecisionsSnapshot.fromJson(mixed), throwsFormatException);
  });
  testWidgets('decisions contrast labels and touch targets', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1280);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final semantics = tester.ensureSemantics();
    final dispose = await openDecisions(
      tester,
      DecisionsController(api: FakeDecisions()),
    );
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
    dispose();
  });
}
