import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'models.dart';

enum FailureKind { offline, degraded, invalid, reset, configuration }

class ApiFailure implements Exception {
  const ApiFailure(this.kind);
  final FailureKind kind;
}

abstract class MarketSocket {
  Stream<Json> get messages;
  Future<void> close();
}

abstract class MarketApi {
  Future<Snapshot> history({
    int? after,
    int? through,
    String? streamId,
    int limit = 200,
    String? symbol,
    String timeframe = '1h',
  });
  Future<MarketSocket> connect(
    String streamId,
    int after, {
    String? symbol,
    String timeframe = '1h',
  });
  void dispose();
}

class HttpMarketApi implements MarketApi {
  HttpMarketApi(this.baseUrl, {http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Uri _endpoint(String path, Map<String, String> query, {bool socket = false}) {
    final base = Uri.tryParse(baseUrl);
    if (base == null ||
        !['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment ||
        (base.path.isNotEmpty && base.path != '/')) {
      throw const ApiFailure(FailureKind.configuration);
    }
    return base.replace(
      scheme: socket ? (base.scheme == 'https' ? 'wss' : 'ws') : base.scheme,
      path: path,
      queryParameters: query,
    );
  }

  @override
  Future<Snapshot> history({
    int? after,
    int? through,
    String? streamId,
    int limit = 200,
    String? symbol,
    String timeframe = '1h',
  }) async {
    final uri = _endpoint('/api/v1/market/candles', {
      'limit': limit.toString(),
      'symbol': ?symbol,
      'timeframe': timeframe,
      if (after != null) 'after': after.toString(),
      if (through != null) 'through': through.toString(),
      'stream_id': ?streamId,
    });
    final response = await _client.get(uri).timeout(const Duration(seconds: 5));
    if (response.statusCode == 409) {
      throw const ApiFailure(FailureKind.reset);
    }
    if (response.statusCode == 503) {
      throw const ApiFailure(FailureKind.degraded);
    }
    if (response.statusCode != 200) {
      throw const ApiFailure(FailureKind.invalid);
    }
    return Snapshot.fromJson(jsonDecode(response.body) as Json);
  }

  @override
  Future<MarketSocket> connect(
    String streamId,
    int after, {
    String? symbol,
    String timeframe = '1h',
  }) async {
    final channel = WebSocketChannel.connect(
      _endpoint('/api/v1/market/events', {
        'stream_id': streamId,
        'after': after.toString(),
        'symbol': ?symbol,
        'timeframe': timeframe,
      }, socket: true),
    );
    try {
      await channel.ready.timeout(const Duration(seconds: 5));
      return _ChannelSocket(channel);
    } catch (_) {
      await channel.sink.close();
      rethrow;
    }
  }

  @override
  void dispose() => _client.close();
}

class _ChannelSocket implements MarketSocket {
  _ChannelSocket(this.channel);
  final WebSocketChannel channel;

  @override
  Stream<Json> get messages =>
      channel.stream.map((message) => jsonDecode(message as String) as Json);

  @override
  Future<void> close() async => channel.sink.close();
}
