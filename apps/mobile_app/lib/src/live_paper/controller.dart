import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'models.dart';

enum LivePaperLoadState { loading, ready, offline, error }

/// Snapshot + periodic refresh. Structured so a future WebSocket layer can
/// push incremental updates into the same fields without rewriting the UI.
class LivePaperController extends ChangeNotifier {
  LivePaperController({
    required this.api,
    this.refreshInterval = const Duration(seconds: 15),
    this.chartSymbol = 'SPY',
    ChartTimeframe? initialChartTimeframe,
    this.autoStart = true,
  }) : chartTimeframe = initialChartTimeframe ?? ChartTimeframe.m15 {
    if (autoStart) {
      unawaited(refresh());
      _armTimer();
    }
  }

  final LivePaperApi api;
  final Duration refreshInterval;
  final String chartSymbol;
  final bool autoStart;

  LivePaperLoadState loadState = LivePaperLoadState.loading;
  String? errorMessage;
  LivePaperDashboard? dashboard;
  List<LiveOrder> orders = const [];
  List<LiveFill> fills = const [];
  LiveCandlesResponse? candles;
  ObserverSummary? observer;
  ChartTimeframe chartTimeframe;
  bool _refreshing = false;
  bool _disposed = false;
  Timer? _timer;

  /// Operational timeframe comes from dashboard; chart TF is view-only.
  String get operationalTimeframe =>
      dashboard?.market.operationalTimeframe ?? '15m';

  Future<void> refresh() async {
    if (_disposed || _refreshing) return;
    _refreshing = true;
    final firstLoad = dashboard == null;
    if (firstLoad) {
      loadState = LivePaperLoadState.loading;
      errorMessage = null;
      notifyListeners();
    }
    try {
      final results = await Future.wait([
        api.fetchDashboard(),
        api.fetchOrders(),
        api.fetchCandles(symbol: chartSymbol, timeframe: chartTimeframe),
        api.fetchObserverSummary(),
      ]);
      if (_disposed) return;
      dashboard = results[0] as LivePaperDashboard;
      orders = results[1] as List<LiveOrder>;
      candles = results[2] as LiveCandlesResponse;
      observer = results[3] as ObserverSummary?;
      // Fills are secondary; keep previous on soft failure.
      try {
        fills = await api.fetchFills();
      } catch (_) {}
      loadState = LivePaperLoadState.ready;
      errorMessage = null;
    } on LivePaperApiException catch (e) {
      if (_disposed) return;
      errorMessage = e.message;
      loadState = e.statusCode == null && dashboard == null
          ? LivePaperLoadState.offline
          : (dashboard == null
                ? LivePaperLoadState.error
                : LivePaperLoadState.ready);
      if (dashboard == null && e.statusCode == null) {
        loadState = LivePaperLoadState.offline;
      } else if (dashboard == null) {
        loadState = LivePaperLoadState.error;
      }
    } catch (e) {
      if (_disposed) return;
      errorMessage = e.toString();
      if (dashboard == null) {
        loadState = LivePaperLoadState.error;
      }
    } finally {
      _refreshing = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> setChartTimeframe(ChartTimeframe timeframe) async {
    if (timeframe == chartTimeframe) return;
    chartTimeframe = timeframe;
    notifyListeners();
    try {
      candles = await api.fetchCandles(
        symbol: chartSymbol,
        timeframe: chartTimeframe,
      );
    } catch (e) {
      errorMessage = e.toString();
    }
    if (!_disposed) notifyListeners();
  }

  void _armTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(refreshInterval, (_) => unawaited(refresh()));
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    api.dispose();
    super.dispose();
  }
}
