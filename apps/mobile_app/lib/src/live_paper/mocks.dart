import 'api.dart';
import 'models.dart';

/// Development / widget-test mocks. Never present as real validation.
class MockLivePaperApi implements LivePaperApi {
  MockLivePaperApi({
    LivePaperDashboard? dashboard,
    List<LiveOrder>? orders,
    List<LiveFill>? fills,
    LiveCandlesResponse? Function(String symbol, ChartTimeframe tf)? candles,
    ObserverSummary? observer,
    this.failDashboard = false,
    this.offline = false,
    this.includeDemoMarkers = false,
  }) : dashboard = dashboard ?? demoDashboard(),
       orders = orders ?? demoOrders(),
       fills = fills ?? const [],
       candlesBuilder = candles,
       observer = observer ?? demoObserverOk();

  LivePaperDashboard dashboard;
  List<LiveOrder> orders;
  List<LiveFill> fills;
  LiveCandlesResponse? Function(String symbol, ChartTimeframe tf)?
  candlesBuilder;
  ObserverSummary? observer;
  bool failDashboard;
  bool offline;
  bool includeDemoMarkers;

  int dashboardCalls = 0;
  ChartTimeframe? lastCandleTimeframe;

  @override
  Future<LivePaperDashboard> fetchDashboard() async {
    dashboardCalls++;
    if (offline) {
      throw const LivePaperApiException('Offline', statusCode: null);
    }
    if (failDashboard) {
      throw const LivePaperApiException('API error', statusCode: 500);
    }
    return dashboard;
  }

  @override
  Future<List<LiveOrder>> fetchOrders() async {
    if (offline || failDashboard) {
      throw const LivePaperApiException('API error', statusCode: 500);
    }
    return orders;
  }

  @override
  Future<List<LiveFill>> fetchFills() async {
    if (offline || failDashboard) {
      throw const LivePaperApiException('API error', statusCode: 500);
    }
    return fills;
  }

  @override
  Future<LiveCandlesResponse> fetchCandles({
    required String symbol,
    required ChartTimeframe timeframe,
    int limit = 200,
  }) async {
    lastCandleTimeframe = timeframe;
    if (offline) {
      throw const LivePaperApiException('Offline', statusCode: null);
    }
    if (candlesBuilder != null) {
      return candlesBuilder!(symbol, timeframe) ??
          LiveCandlesResponse(
            symbol: symbol,
            timeframe: timeframe.apiValue,
            candles: const [],
          );
    }
    return demoCandles(
      symbol: symbol,
      timeframe: timeframe,
      includeMarkers: includeDemoMarkers,
    );
  }

  @override
  Future<ObserverSummary?> fetchObserverSummary() async => observer;

  @override
  void dispose() {}
}

LivePaperDashboard demoDashboard({
  MarketStatus market = MarketStatus.open,
  bool brokerConnected = true,
  bool riskPaused = false,
  bool riskDegraded = false,
  String? dayPnl = '24.81',
  String? totalPnl = '324.21',
  List<LivePosition>? positions,
  LiveLatestDecision? decision,
  String? lastBarUtc,
}) {
  final now = DateTime.now().toUtc();
  return LivePaperDashboard(
    schemaVersion: '1.0',
    mode: LivePaperMode.alpacaPaper,
    simulatedMoney: true,
    broker: LiveBrokerInfo(
      name: 'alpaca',
      connected: brokerConnected,
      lastSyncUtc: now.subtract(const Duration(seconds: 12)),
      degradedReason: brokerConnected ? null : 'broker unreachable',
    ),
    market: LiveMarketInfo(
      status: market,
      provider: 'alpaca',
      feed: 'iex',
      lastBarUtc: lastBarUtc != null
          ? DateTime.parse(lastBarUtc)
          : now.subtract(const Duration(minutes: 2)),
      operationalTimeframe: '15m',
    ),
    account: LiveAccountInfo(
      currency: 'USD',
      equity: '100324.21',
      cash: '97401.33',
      buyingPower: '97401.33',
      dayPnl: dayPnl,
      totalPnl: totalPnl,
    ),
    risk: LiveRiskInfo(
      paused: riskPaused,
      degraded: riskDegraded,
      reason: riskPaused
          ? 'manual pause'
          : riskDegraded
          ? 'execution path degraded'
          : null,
    ),
    latestDecision:
        decision ??
        LiveLatestDecision(
          symbol: 'AAPL',
          timeframe: '15m',
          signal: 'BUY',
          risk: 'APPROVED',
          reason: 'baseline strategy',
          createdAt: now.subtract(const Duration(minutes: 2)),
          strategyVersion: 'v1',
        ),
    positions:
        positions ??
        [
          LivePosition(
            symbol: 'TSLA',
            qty: '3',
            avgEntryPrice: '305.18',
            marketValue: '920.00',
            unrealizedPnl: '4.46',
            unrealizedPnlPct: '0.48',
          ),
        ],
    updatedAt: now,
  );
}

List<LiveOrder> demoOrders() {
  final now = DateTime.now().toUtc();
  return [
    LiveOrder(
      orderId: 'ord-1',
      symbol: 'AAPL',
      side: 'BUY',
      qty: '2',
      filledQty: '2',
      status: OrderStatus.filled,
      submittedAt: now.subtract(const Duration(minutes: 5)),
      fillPrice: '198.42',
    ),
    LiveOrder(
      orderId: 'ord-2',
      symbol: 'MSFT',
      side: 'SELL',
      qty: '5',
      filledQty: '2',
      status: OrderStatus.partial,
      submittedAt: now.subtract(const Duration(minutes: 12)),
      fillPrice: '420.10',
    ),
    LiveOrder(
      orderId: 'ord-3',
      symbol: 'NVDA',
      side: 'BUY',
      qty: '1',
      filledQty: '0',
      status: OrderStatus.rejected,
      submittedAt: now.subtract(const Duration(minutes: 20)),
    ),
  ];
}

ObserverSummary demoObserverOk() => ObserverSummary(
  status: 'OK',
  regime: 'TRENDING',
  confidence: 0.72,
  lastAnalysisAt: DateTime.now().toUtc().subtract(const Duration(minutes: 8)),
  note: 'Observer only',
);

ObserverSummary demoObserverDegraded() => ObserverSummary(
  status: 'DEGRADED',
  regime: null,
  confidence: null,
  lastAnalysisAt: DateTime.now().toUtc().subtract(const Duration(minutes: 30)),
  note: 'TIMEOUT',
);

LiveCandlesResponse demoCandles({
  required String symbol,
  required ChartTimeframe timeframe,
  bool includeMarkers = false,
}) {
  final step = switch (timeframe) {
    ChartTimeframe.m5 => const Duration(minutes: 5),
    ChartTimeframe.m15 => const Duration(minutes: 15),
    ChartTimeframe.h1 => const Duration(hours: 1),
  };
  final end = DateTime.now().toUtc().subtract(step);
  final candles = <LiveCandle>[];
  var price = 520.0;
  for (var i = 0; i < 48; i++) {
    final openTime = end.subtract(step * (47 - i));
    final open = price;
    final close = price + ((i % 5) - 2) * 0.35;
    final high = open > close ? open + 0.4 : close + 0.4;
    final low = open < close ? open - 0.4 : close - 0.4;
    candles.add(
      LiveCandle(
        openTime: openTime,
        closeTime: openTime.add(step),
        open: open.toStringAsFixed(2),
        high: high.toStringAsFixed(2),
        low: low.toStringAsFixed(2),
        close: close.toStringAsFixed(2),
        volume: 1000 + i * 10,
        symbol: symbol,
        timeframe: timeframe.apiValue,
      ),
    );
    price = close;
  }
  final markers = includeMarkers
      ? [
          ChartMarker(
            time: candles[20].closeTime,
            side: 'BUY',
            price: candles[20].close,
            symbol: symbol,
          ),
          ChartMarker(
            time: candles[35].closeTime,
            side: 'SELL',
            price: candles[35].close,
            symbol: symbol,
          ),
        ]
      : const <ChartMarker>[];
  return LiveCandlesResponse(
    symbol: symbol,
    timeframe: timeframe.apiValue,
    candles: candles,
    markers: markers,
  );
}
