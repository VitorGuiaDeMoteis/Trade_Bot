import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class LivePaperApiException implements Exception {
  const LivePaperApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

abstract class LivePaperApi {
  Future<LivePaperDashboard> fetchDashboard();
  Future<List<LiveOrder>> fetchOrders();
  Future<List<LiveFill>> fetchFills();
  Future<LiveCandlesResponse> fetchCandles({
    required String symbol,
    required ChartTimeframe timeframe,
    int limit = 200,
  });
  Future<ObserverSummary?> fetchObserverSummary();
  void dispose();
}

class HttpLivePaperApi implements LivePaperApi {
  HttpLivePaperApi(this.baseUrl, {http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = Uri.tryParse(baseUrl);
    if (base == null ||
        !['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty) {
      throw const LivePaperApiException(
        'API_BASE_URL inválido ou não configurado.',
        statusCode: null,
      );
    }
    return base.replace(path: path, queryParameters: query);
  }

  Future<Json> _get(String path, [Map<String, String>? query]) async {
    final response = await _client
        .get(_uri(path, query))
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      throw LivePaperApiException(
        'HTTP ${response.statusCode}',
        statusCode: response.statusCode,
      );
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw const LivePaperApiException('Resposta JSON inválida.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  @override
  Future<LivePaperDashboard> fetchDashboard() async {
    final json = await _get('/api/v1/live-paper/dashboard');
    return LivePaperDashboard.fromJson(json);
  }

  @override
  Future<List<LiveOrder>> fetchOrders() async {
    final json = await _get('/api/v1/live-paper/orders');
    final list = json['orders'] ?? json['items'] ?? const [];
    if (list is! List) return const [];
    return list
        .map((item) => LiveOrder.fromJson(Map<String, dynamic>.from(item as Map)))
        .toList();
  }

  @override
  Future<List<LiveFill>> fetchFills() async {
    final json = await _get('/api/v1/live-paper/fills');
    final list = json['fills'] ?? json['items'] ?? const [];
    if (list is! List) return const [];
    return list
        .map((item) => LiveFill.fromJson(Map<String, dynamic>.from(item as Map)))
        .toList();
  }

  @override
  Future<LiveCandlesResponse> fetchCandles({
    required String symbol,
    required ChartTimeframe timeframe,
    int limit = 200,
  }) async {
    final json = await _get('/api/v1/market/candles', {
      'symbol': symbol,
      'timeframe': timeframe.apiValue,
      'limit': '$limit',
    });
    // Prefer nested candles; fall back if snapshot-shaped.
    if (json.containsKey('candles') || json.containsKey('bars')) {
      return LiveCandlesResponse.fromJson({
        ...json,
        'symbol': json['symbol'] ?? symbol,
        'timeframe': json['timeframe'] ?? timeframe.apiValue,
      });
    }
    return LiveCandlesResponse(
      symbol: symbol,
      timeframe: timeframe.apiValue,
      candles: const [],
      markers: const [],
    );
  }

  @override
  Future<ObserverSummary?> fetchObserverSummary() async {
    try {
      final response = await _client
          .get(_uri('/api/v1/observer/status'))
          .timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) return null;
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return null;
      final map = Map<String, dynamic>.from(decoded);
      // Optionally enrich with latest analysis regime.
      try {
        final analyses = await _client
            .get(_uri('/api/v1/observer/analyses'))
            .timeout(const Duration(seconds: 5));
        if (analyses.statusCode == 200) {
          final list = jsonDecode(analyses.body);
          if (list is List && list.isNotEmpty) {
            final first = Map<String, dynamic>.from(list.first as Map);
            map['regime'] ??= first['regime'];
            map['confidence'] ??= first['confidence'];
            map['last_analysis_at'] ??= first['created_at'];
          }
        }
      } catch (_) {
        // Observer summary is best-effort.
      }
      return ObserverSummary.fromJson(map);
    } catch (_) {
      return null;
    }
  }

  @override
  void dispose() => _client.close();
}
