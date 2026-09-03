import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/app.dart';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/controller.dart';
import 'package:mobile_app/src/market/models.dart';
import 'support/market_fake.dart';

Json realStatus(
  String symbol, {
  String state = 'connected',
  String database = 'up',
}) => {
  ...statusJson(stream: 'series-$symbol', database: database),
  'market_data': {
    'state': state,
    'provider': 'alpaca',
    'feed': 'iex',
    'symbols': ['SPY', 'AAPL', 'TSLA'],
  },
};

Snapshot realSnapshot(
  String symbol, {
  List<int> sequences = const [1, 2],
  int? cursor,
}) {
  final data = snapshotJson(
    sequences,
    stream: 'series-$symbol',
    cursor: cursor,
  );
  data['symbol'] = symbol;
  data['market_data'] = realStatus(symbol)['market_data'];
  data['candles'] = sequences
      .map(
        (sequence) => {
          ...candleJson(sequence, stream: 'series-$symbol'),
          'symbol': symbol,
          'provider': 'alpaca',
          'regime': null,
          'candle_id': '$symbol-$sequence',
        },
      )
      .toList();
  return Snapshot.fromJson(data);
}

class SeriesApi extends FakeApi {
  final pending = <String, Completer<Snapshot>>{};
  final seriesRequests = <String>[];
  @override
  Future<Snapshot> history({
    int? after,
    int? through,
    String? streamId,
    int limit = 200,
    String? symbol,
    String timeframe = '1h',
  }) async {
    final selected = symbol ?? 'SPY';
    seriesRequests.add(selected);
    if (pending.containsKey(selected)) return pending[selected]!.future;
    return realSnapshot(
      selected,
      sequences: after == null ? [1, 2] : [],
      cursor: after,
    );
  }

  @override
  Future<MarketSocket> connect(
    String streamId,
    int after, {
    String? symbol,
    String timeframe = '1h',
  }) async {
    final socket = FakeSocket();
    sockets.add(socket);
    socket.add(realStatus(symbol!));
    return socket;
  }
}

void main() {
  testWidgets(
    'seleção consulta REST independente e reinicia cursor por ativo',
    (tester) async {
      final api = SeriesApi();
      final controller = MarketController(api: api);
      await controller.start();
      await tester.pump();
      expect(controller.selectedSymbol, 'SPY');
      final firstSocket = api.sockets.last;
      for (final symbol in ['AAPL', 'TSLA', 'SPY']) {
        controller.setSymbol(symbol);
        expect(controller.candles, isEmpty);
        expect(controller.cursor, 0);
        await tester.pump();
        expect(controller.streamId, 'series-$symbol');
        expect(controller.cursor, 2);
        expect(controller.candles.map((c) => c.symbol).toSet(), {symbol});
      }
      expect(firstSocket.closed, isTrue);
      expect(api.seriesRequests, ['SPY', 'AAPL', 'TSLA', 'SPY']);
      controller.dispose();
    },
  );

  testWidgets('resposta atrasada de ativo anterior não contamina a seleção', (
    tester,
  ) async {
    final api = SeriesApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    final pending = Completer<Snapshot>();
    api.pending['AAPL'] = pending;
    controller.setSymbol('AAPL');
    await tester.pump();
    controller.setSymbol('TSLA');
    await tester.pump();
    pending.complete(realSnapshot('AAPL'));
    await tester.pump();
    expect(controller.selectedSymbol, 'TSLA');
    expect(controller.candles.every((c) => c.symbol == 'TSLA'), isTrue);
    expect(controller.state, MarketConnectionState.connected);
    controller.dispose();
  });

  testWidgets('mercado fechado é neutro e banco indisponível prevalece', (
    tester,
  ) async {
    final api = SeriesApi();
    final controller = MarketController(api: api);
    await tester.pumpWidget(TradingBotApp(controller: controller));
    await tester.pump();
    api.sockets.last.add(realStatus('SPY', state: 'market_closed'));
    await tester.pump();
    expect(find.text('Sessão regular fechada'), findsOneWidget);
    expect(find.byKey(const Key('retry-button')), findsNothing);
    expect(controller.candles.length, 2);
    api.sockets.last.add(
      realStatus('SPY', state: 'market_closed', database: 'down'),
    );
    await tester.pump();
    expect(controller.state, MarketConnectionState.degraded);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets('payload de outro ativo e candle parcial são rejeitados', (
    tester,
  ) async {
    final api = SeriesApi();
    final controller = MarketController(api: api);
    await controller.start();
    await tester.pump();
    final event = eventJson(3);
    event['stream_id'] = 'series-SPY';
    event['payload'] = {
      ...candleJson(3, stream: 'series-SPY'),
      'symbol': 'AAPL',
      'provider': 'alpaca',
    };
    api.sockets.last.add(event);
    await tester.pump();
    expect(controller.state, MarketConnectionState.configurationError);
    expect(controller.cursor, 2);
    expect(
      () => Candle.fromJson({...candleJson(3), 'is_closed': false}),
      throwsFormatException,
    );
    controller.dispose();
  });

  testWidgets(
    'cursor segue ingestão enquanto gráfico ordena tempo de mercado',
    (tester) async {
      final api = SeriesApi();
      final controller = MarketController(api: api);
      await controller.start();
      await tester.pump();
      final old = DateTime.utc(2025, 12, 31, 23);
      api.sockets.last.add({
        ...eventJson(3),
        'stream_id': 'series-SPY',
        'payload': {
          ...candleJson(3, stream: 'series-SPY'),
          'symbol': 'SPY',
          'provider': 'alpaca',
          'candle_id': 'SPY-late',
          'open_time': old.toIso8601String(),
          'close_time': old.add(const Duration(hours: 1)).toIso8601String(),
        },
      });
      await tester.pump();
      expect(controller.cursor, 3);
      expect(controller.filteredCandles.first.id, 'SPY-late');
      controller.dispose();
    },
  );

  for (final size in [
    const Size(320, 568),
    const Size(800, 1280),
    const Size(1280, 800),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('seletor Alpaca sem overflow $size escala $scale', (
        tester,
      ) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = size;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final controller = MarketController(api: SeriesApi());
        await tester.pumpWidget(TradingBotApp(controller: controller));
        await tester.pump();
        expect(find.text('DADOS REAIS'), findsOneWidget);
        expect(find.text('SIMULADO'), findsNothing);
        final chip = find.widgetWithText(ChoiceChip, 'AAPL');
        await tester.ensureVisible(chip);
        await tester.pump();
        expect(tester.getSize(chip).height, greaterThanOrEqualTo(48));
        await tester.tap(chip);
        await tester.pump();
        expect(controller.selectedSymbol, 'AAPL');
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        controller.dispose();
      });
    }
  }
}
