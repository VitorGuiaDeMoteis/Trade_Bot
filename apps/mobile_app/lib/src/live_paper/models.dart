typedef Json = Map<String, dynamic>;

/// Frozen Live Paper dashboard contract (schema 1.0).
/// Monetary fields stay as Decimal strings; parse only for display formatting.

enum LivePaperMode {
  alpacaPaper,
  localPaper,
  backtest,
  aiObserver,
  unknown,
}

LivePaperMode parseLivePaperMode(String? raw) {
  switch (raw) {
    case 'ALPACA_PAPER':
      return LivePaperMode.alpacaPaper;
    case 'LOCAL_PAPER':
      return LivePaperMode.localPaper;
    case 'BACKTEST':
      return LivePaperMode.backtest;
    case 'AI_OBSERVER':
      return LivePaperMode.aiObserver;
    default:
      return LivePaperMode.unknown;
  }
}

enum MarketStatus { open, closed, degraded, unknown }

MarketStatus parseMarketStatus(String? raw) {
  switch (raw?.toUpperCase()) {
    case 'OPEN':
      return MarketStatus.open;
    case 'CLOSED':
      return MarketStatus.closed;
    case 'DEGRADED':
      return MarketStatus.degraded;
    default:
      return MarketStatus.unknown;
  }
}

enum RiskLevel { normal, paused, degraded }

RiskLevel riskLevelFromFlags({required bool paused, required bool degraded}) {
  if (paused) return RiskLevel.paused;
  if (degraded) return RiskLevel.degraded;
  return RiskLevel.normal;
}

enum OrderStatus { pending, partial, filled, canceled, rejected, unknown }

OrderStatus parseOrderStatus(String? raw) {
  switch (raw?.toUpperCase()) {
    case 'PENDING':
    case 'NEW':
    case 'ACCEPTED':
      return OrderStatus.pending;
    case 'PARTIAL':
    case 'PARTIALLY_FILLED':
      return OrderStatus.partial;
    case 'FILLED':
      return OrderStatus.filled;
    case 'CANCELED':
    case 'CANCELLED':
      return OrderStatus.canceled;
    case 'REJECTED':
      return OrderStatus.rejected;
    default:
      return OrderStatus.unknown;
  }
}

enum ChartTimeframe { m5, m15, h1 }

extension ChartTimeframeX on ChartTimeframe {
  String get apiValue => switch (this) {
    ChartTimeframe.m5 => '5m',
    ChartTimeframe.m15 => '15m',
    ChartTimeframe.h1 => '1h',
  };

  String get label => apiValue;
}

ChartTimeframe parseChartTimeframe(String? raw) {
  switch (raw) {
    case '5m':
      return ChartTimeframe.m5;
    case '15m':
      return ChartTimeframe.m15;
    case '1h':
      return ChartTimeframe.h1;
    default:
      return ChartTimeframe.m15;
  }
}

class LiveBrokerInfo {
  LiveBrokerInfo({
    required this.name,
    required this.connected,
    this.lastSyncUtc,
    this.degradedReason,
  });

  factory LiveBrokerInfo.fromJson(Json json) => LiveBrokerInfo(
    name: (json['name'] as String?) ?? 'unknown',
    connected: json['connected'] == true,
    lastSyncUtc: _parseDate(json['last_sync_utc']),
    degradedReason: json['degraded_reason'] as String?,
  );

  final String name;
  final bool connected;
  final DateTime? lastSyncUtc;
  final String? degradedReason;
}

class LiveMarketInfo {
  LiveMarketInfo({
    required this.status,
    this.provider,
    this.feed,
    this.lastBarUtc,
    this.operationalTimeframe = '15m',
  });

  factory LiveMarketInfo.fromJson(Json json) => LiveMarketInfo(
    status: parseMarketStatus(json['status'] as String?),
    provider: json['provider'] as String?,
    feed: json['feed'] as String?,
    lastBarUtc: _parseDate(json['last_bar_utc']),
    operationalTimeframe:
        (json['operational_timeframe'] as String?) ?? '15m',
  );

  final MarketStatus status;
  final String? provider;
  final String? feed;
  final DateTime? lastBarUtc;
  final String operationalTimeframe;

  bool isStale({
    DateTime? now,
    Duration threshold = const Duration(minutes: 20),
  }) {
    if (lastBarUtc == null) return false;
    final reference = now ?? DateTime.now().toUtc();
    return reference.difference(lastBarUtc!.toUtc()) > threshold;
  }
}

class LiveAccountInfo {
  LiveAccountInfo({
    required this.currency,
    this.equity,
    this.cash,
    this.buyingPower,
    this.dayPnl,
    this.totalPnl,
  });

  factory LiveAccountInfo.fromJson(Json json) => LiveAccountInfo(
    currency: (json['currency'] as String?) ?? 'USD',
    equity: _asDecimalString(json['equity']),
    cash: _asDecimalString(json['cash']),
    buyingPower: _asDecimalString(json['buying_power']),
    dayPnl: _asDecimalString(json['day_pnl']),
    totalPnl: _asDecimalString(json['total_pnl']),
  );

  final String currency;
  final String? equity;
  final String? cash;
  final String? buyingPower;
  final String? dayPnl;
  final String? totalPnl;
}

class LiveRiskInfo {
  LiveRiskInfo({
    required this.paused,
    required this.degraded,
    this.reason,
  });

  factory LiveRiskInfo.fromJson(Json json) => LiveRiskInfo(
    paused: json['paused'] == true,
    degraded: json['degraded'] == true,
    reason: json['reason'] as String?,
  );

  final bool paused;
  final bool degraded;
  final String? reason;

  RiskLevel get level =>
      riskLevelFromFlags(paused: paused, degraded: degraded);
}

class LiveLatestDecision {
  LiveLatestDecision({
    required this.symbol,
    required this.timeframe,
    required this.signal,
    required this.risk,
    this.reason,
    this.createdAt,
    this.strategyVersion,
  });

  factory LiveLatestDecision.fromJson(Json json) => LiveLatestDecision(
    symbol: (json['symbol'] as String?) ?? '—',
    timeframe: (json['timeframe'] as String?) ?? '—',
    signal: (json['signal'] as String?) ?? 'HOLD',
    risk: (json['risk'] as String?) ?? 'UNKNOWN',
    reason: json['reason'] as String?,
    createdAt: _parseDate(json['created_at']),
    strategyVersion: json['strategy_version'] as String?,
  );

  final String symbol;
  final String timeframe;
  final String signal;
  final String risk;
  final String? reason;
  final DateTime? createdAt;
  final String? strategyVersion;
}

class LivePosition {
  LivePosition({
    required this.symbol,
    required this.qty,
    this.avgEntryPrice,
    this.marketValue,
    this.unrealizedPnl,
    this.unrealizedPnlPct,
  });

  factory LivePosition.fromJson(Json json) => LivePosition(
    symbol: (json['symbol'] as String?) ?? '—',
    qty: _asDecimalString(json['qty']) ?? '0',
    avgEntryPrice: _asDecimalString(json['avg_entry_price']),
    marketValue: _asDecimalString(json['market_value']),
    unrealizedPnl: _asDecimalString(json['unrealized_pnl']),
    unrealizedPnlPct: _asDecimalString(json['unrealized_pnl_pct']),
  );

  final String symbol;
  final String qty;
  final String? avgEntryPrice;
  final String? marketValue;
  final String? unrealizedPnl;
  final String? unrealizedPnlPct;
}

class LivePaperDashboard {
  LivePaperDashboard({
    required this.schemaVersion,
    required this.mode,
    required this.simulatedMoney,
    required this.broker,
    required this.market,
    required this.account,
    required this.risk,
    this.latestDecision,
    required this.positions,
    this.updatedAt,
  });

  factory LivePaperDashboard.fromJson(Json json) {
    final positionsRaw = json['positions'];
    return LivePaperDashboard(
      schemaVersion: (json['schema_version'] as String?) ?? '1.0',
      mode: parseLivePaperMode(json['mode'] as String?),
      simulatedMoney: json['simulated_money'] == true,
      broker: LiveBrokerInfo.fromJson(
        Map<String, dynamic>.from((json['broker'] as Map?) ?? const {}),
      ),
      market: LiveMarketInfo.fromJson(
        Map<String, dynamic>.from((json['market'] as Map?) ?? const {}),
      ),
      account: LiveAccountInfo.fromJson(
        Map<String, dynamic>.from((json['account'] as Map?) ?? const {}),
      ),
      risk: LiveRiskInfo.fromJson(
        Map<String, dynamic>.from((json['risk'] as Map?) ?? const {}),
      ),
      latestDecision: json['latest_decision'] == null
          ? null
          : LiveLatestDecision.fromJson(
              Map<String, dynamic>.from(json['latest_decision'] as Map),
            ),
      positions: positionsRaw is List
          ? positionsRaw
                .map(
                  (item) => LivePosition.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ),
                )
                .toList()
          : const [],
      updatedAt: _parseDate(json['updated_at']),
    );
  }

  final String schemaVersion;
  final LivePaperMode mode;
  final bool simulatedMoney;
  final LiveBrokerInfo broker;
  final LiveMarketInfo market;
  final LiveAccountInfo account;
  final LiveRiskInfo risk;
  final LiveLatestDecision? latestDecision;
  final List<LivePosition> positions;
  final DateTime? updatedAt;
}

class LiveOrder {
  LiveOrder({
    required this.orderId,
    required this.symbol,
    required this.side,
    required this.qty,
    this.filledQty,
    required this.status,
    this.submittedAt,
    this.fillPrice,
  });

  factory LiveOrder.fromJson(Json json) => LiveOrder(
    orderId: (json['order_id'] as String?) ?? '',
    symbol: (json['symbol'] as String?) ?? '—',
    side: (json['side'] as String?) ?? '—',
    qty: _asDecimalString(json['qty']) ?? '0',
    filledQty: _asDecimalString(json['filled_qty']),
    status: parseOrderStatus(json['status'] as String?),
    submittedAt: _parseDate(json['submitted_at'] ?? json['created_at']),
    fillPrice: _asDecimalString(json['fill_price'] ?? json['avg_fill_price']),
  );

  final String orderId;
  final String symbol;
  final String side;
  final String qty;
  final String? filledQty;
  final OrderStatus status;
  final DateTime? submittedAt;
  final String? fillPrice;

  String get statusLabel => switch (status) {
    OrderStatus.pending => 'PENDING',
    OrderStatus.partial => 'PARTIAL',
    OrderStatus.filled => 'FILLED',
    OrderStatus.canceled => 'CANCELED',
    OrderStatus.rejected => 'REJECTED',
    OrderStatus.unknown => 'UNKNOWN',
  };
}

class LiveFill {
  LiveFill({
    required this.fillId,
    required this.orderId,
    required this.symbol,
    required this.side,
    required this.qty,
    required this.price,
    this.filledAt,
  });

  factory LiveFill.fromJson(Json json) => LiveFill(
    fillId: (json['fill_id'] as String?) ?? '',
    orderId: (json['order_id'] as String?) ?? '',
    symbol: (json['symbol'] as String?) ?? '—',
    side: (json['side'] as String?) ?? '—',
    qty: _asDecimalString(json['qty']) ?? '0',
    price: _asDecimalString(json['price']) ?? '0',
    filledAt: _parseDate(json['filled_at']),
  );

  final String fillId;
  final String orderId;
  final String symbol;
  final String side;
  final String qty;
  final String price;
  final DateTime? filledAt;
}

/// Flexible candle for live-paper multi-timeframe chart (5m / 15m / 1h).
class LiveCandle {
  LiveCandle({
    required this.openTime,
    required this.closeTime,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    this.volume,
    this.symbol,
    this.timeframe,
  });

  factory LiveCandle.fromJson(Json json) {
    final openTime =
        _parseDate(json['open_time'] ?? json['t'] ?? json['timestamp']) ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
    final closeTime =
        _parseDate(json['close_time']) ??
        openTime.add(const Duration(minutes: 1));
    return LiveCandle(
      openTime: openTime,
      closeTime: closeTime,
      open: _asDecimalString(json['open'] ?? json['o']) ?? '0',
      high: _asDecimalString(json['high'] ?? json['h']) ?? '0',
      low: _asDecimalString(json['low'] ?? json['l']) ?? '0',
      close: _asDecimalString(json['close'] ?? json['c']) ?? '0',
      volume: json['volume'] is int
          ? json['volume'] as int
          : int.tryParse('${json['volume'] ?? ''}'),
      symbol: json['symbol'] as String?,
      timeframe: json['timeframe'] as String?,
    );
  }

  final DateTime openTime;
  final DateTime closeTime;
  final String open;
  final String high;
  final String low;
  final String close;
  final int? volume;
  final String? symbol;
  final String? timeframe;
}

/// Chart trade markers. Empty list from API means no markers — never invent.
class ChartMarker {
  ChartMarker({
    required this.time,
    required this.side,
    this.price,
    this.symbol,
  });

  factory ChartMarker.fromJson(Json json) => ChartMarker(
    time:
        _parseDate(json['time'] ?? json['at'] ?? json['created_at']) ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    side: ((json['side'] as String?) ?? 'BUY').toUpperCase(),
    price: _asDecimalString(json['price']),
    symbol: json['symbol'] as String?,
  );

  final DateTime time;
  final String side; // BUY | SELL
  final String? price;
  final String? symbol;
}

class LiveCandlesResponse {
  LiveCandlesResponse({
    required this.symbol,
    required this.timeframe,
    required this.candles,
    this.markers = const [],
  });

  factory LiveCandlesResponse.fromJson(Json json) {
    final list = json['candles'] ?? json['bars'] ?? const [];
    final markersRaw = json['markers'];
    return LiveCandlesResponse(
      symbol: (json['symbol'] as String?) ?? 'SPY',
      timeframe: (json['timeframe'] as String?) ?? '15m',
      candles: list is List
          ? list
                .map(
                  (item) => LiveCandle.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ),
                )
                .toList()
          : const [],
      markers: markersRaw is List
          ? markersRaw
                .map(
                  (item) => ChartMarker.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ),
                )
                .toList()
          : const [],
    );
  }

  final String symbol;
  final String timeframe;
  final List<LiveCandle> candles;
  final List<ChartMarker> markers;
}

class ObserverSummary {
  ObserverSummary({
    required this.status,
    this.regime,
    this.confidence,
    this.lastAnalysisAt,
    this.note,
  });

  factory ObserverSummary.fromJson(Json json) => ObserverSummary(
    status: (json['status'] as String?) ?? 'UNKNOWN',
    regime: json['regime'] as String?,
    confidence: (json['confidence'] as num?)?.toDouble(),
    lastAnalysisAt: _parseDate(json['last_analysis_at'] ?? json['as_of_utc']),
    note: json['note'] as String?,
  );

  final String status;
  final String? regime;
  final double? confidence;
  final DateTime? lastAnalysisAt;
  final String? note;

  bool get isDegraded =>
      status.toUpperCase() == 'DEGRADED' ||
      status.toUpperCase() == 'TIMEOUT' ||
      status.toUpperCase() == 'ERROR';
}

DateTime? _parseDate(Object? raw) {
  if (raw == null) return null;
  if (raw is DateTime) return raw.toUtc();
  try {
    return DateTime.parse(raw.toString()).toUtc();
  } catch (_) {
    return null;
  }
}

String? _asDecimalString(Object? raw) {
  if (raw == null) return null;
  final text = raw.toString().trim();
  if (text.isEmpty || text.toLowerCase() == 'null') return null;
  return text;
}
