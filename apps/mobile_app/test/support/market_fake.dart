import 'dart:async';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/models.dart';

Json candleJson(int sequence, {String stream = 'stream-1'}) {
  final start = DateTime.utc(2026).add(Duration(hours: sequence - 1));
  return {
    'candle_id': 'candle-$sequence',
    'stream_id': stream,
    'sequence': sequence,
    'symbol': 'TEST',
    'timeframe': '1h',
    'open_time': start.toIso8601String(),
    'close_time': start.add(const Duration(hours: 1)).toIso8601String(),
    'open': '100.0000',
    'high': '102.0000',
    'low': '99.0000',
    'close': '101.0000',
    'volume': 120,
    'regime': 'uptrend',
    'provider': 'simulator',
    'is_closed': true,
  };
}

Json simulationJson([String state = 'running']) => {
  'state': state,
  'accelerated': true,
  'provider': 'simulator',
  'symbols': ['TEST'],
  'interval_seconds': 2,
};
Json snapshotJson(
  List<int> sequences, {
  String stream = 'stream-1',
  int? cursor,
  int? high,
  String state = 'running',
}) {
  final last = cursor ?? (sequences.isEmpty ? 0 : sequences.last);
  return {
    'schema_version': '2.0',
    'symbol': 'TEST',
    'timeframe': '1h',
    'stream_id': stream,
    'candles': sequences.map((i) => candleJson(i, stream: stream)).toList(),
    'cursor': last,
    'high_watermark': high ?? last,
    'has_more': (high ?? last) > last,
    'last_updated_at': '2026-09-03T12:00:00Z',
    'market_data': simulationJson(state),
  };
}

Json eventJson(int sequence) => {
  'type': 'event',
  'schema_version': '2.0',
  'event_id': 'event-$sequence',
  'event_type': 'market.candle.closed',
  'stream_id': 'stream-1',
  'sequence': sequence,
  'occurred_at': '2026-09-03T12:00:02Z',
  'correlation_id': 'correlation-1',
  'payload': candleJson(sequence),
};
Json statusJson({
  String state = 'running',
  String database = 'up',
  String stream = 'stream-1',
}) => {
  'type': 'stream.status',
  'schema_version': '2.0',
  'stream_id': stream,
  'database': database,
  'market_data': simulationJson(state),
};

class FakeSocket implements MarketSocket {
  final events = StreamController<Json>();
  bool closed = false;
  @override
  Stream<Json> get messages => events.stream;
  void add(Json event) => events.add(event);
  @override
  Future<void> close() async {
    if (closed) return;
    closed = true;
    await events.close();
  }
}

class FakeApi implements MarketApi {
  FakeApi({this.initial = const [1, 2, 3]});
  final List<int> initial;
  final requests = <({int? after, int? through, String? stream})>[];
  final requestedSymbols = <String?>[];
  final sockets = <FakeSocket>[];
  final responses = <Future<Snapshot> Function()>[];
  final connectCursors = <int>[];
  @override
  Future<Snapshot> history({
    int? after,
    int? through,
    String? streamId,
    int limit = 200,
    String? symbol,
    String timeframe = '1h',
  }) async {
    requestedSymbols.add(symbol);
    requests.add((after: after, through: through, stream: streamId));
    if (responses.isNotEmpty) return responses.removeAt(0)();
    return Snapshot.fromJson(
      snapshotJson(after == null ? initial : [], cursor: after),
    );
  }

  @override
  Future<MarketSocket> connect(
    String streamId,
    int after, {
    String? symbol,
    String timeframe = '1h',
  }) async {
    connectCursors.add(after);
    final socket = FakeSocket();
    sockets.add(socket);
    socket.add(statusJson(stream: streamId));
    return socket;
  }

  @override
  void dispose() {}
}
