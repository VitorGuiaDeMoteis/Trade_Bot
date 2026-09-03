typedef Json = Map<String, dynamic>;

enum MarketConnectionState {
  loading,
  connecting,
  connected,
  reconnecting,
  marketClosed,
  delayed,
  degraded,
  offline,
  configurationError,
}

MarketConnectionState parseMarketState(String raw) {
  switch (raw) {
    case 'connected':
    case 'running':
    case 'live':
      return MarketConnectionState.connected;
    case 'connecting':
      return MarketConnectionState.connecting;
    case 'reconnecting':
      return MarketConnectionState.reconnecting;
    case 'market_closed':
      return MarketConnectionState.marketClosed;
    case 'delayed':
      return MarketConnectionState.delayed;
    case 'stopped':
    case 'stalled':
    case 'degraded':
      return MarketConnectionState.degraded;
    case 'configuration_error':
    case 'error':
      return MarketConnectionState.configurationError;
    case 'offline':
    default:
      return MarketConnectionState.offline;
  }
}

class Candle {
  Candle.fromJson(Json json)
    : id = json['candle_id'] as String,
      streamId = json['stream_id'] as String,
      sequence = json['sequence'] as int,
      openTime = DateTime.parse(json['open_time'] as String),
      closeTime = DateTime.parse(json['close_time'] as String),
      open = json['open'] as String,
      high = json['high'] as String,
      low = json['low'] as String,
      close = json['close'] as String,
      volume = json['volume'] as int,
      regime = json['regime'] as String?,
      isClosed = json['is_closed'] as bool,
      symbol = json['symbol'] as String,
      timeframe = json['timeframe'] as String,
      provider = json['provider'] as String {
    final prices = [open, high, low, close].map(double.parse).toList();
    if (!isClosed ||
        timeframe != '1h' ||
        closeTime.difference(openTime) != const Duration(hours: 1) ||
        sequence < 1 ||
        volume < 0 ||
        !openTime.isUtc ||
        !closeTime.isUtc ||
        prices.any((value) => !value.isFinite || value <= 0) ||
        prices[1] < prices[0] ||
        prices[1] < prices[3] ||
        prices[2] > prices[0] ||
        prices[2] > prices[3]) {
      throw const FormatException('Candle inválido');
    }
  }

  final String id,
      streamId,
      open,
      high,
      low,
      close,
      symbol,
      timeframe,
      provider;
  final String? regime;
  final bool isClosed;
  final int sequence, volume;
  final DateTime openTime, closeTime;
}

class MarketDataInfo {
  MarketDataInfo.fromJson(Json json)
    : state = json['state'] as String,
      connectionState = parseMarketState(json['state'] as String),
      provider = json['provider'] as String?,
      feed = json['feed'] as String?,
      symbols = (json['symbols'] as List?)?.cast<String>(),
      accelerated = json['accelerated'] == true;

  final bool accelerated;
  final String state;
  final MarketConnectionState connectionState;
  final String? provider;
  final String? feed;
  final List<String>? symbols;
}

class Snapshot {
  Snapshot.fromJson(Json json)
    : streamId = json['stream_id'] as String,
      symbol = json['symbol'] as String,
      timeframe = json['timeframe'] as String,
      candles = (json['candles'] as List)
          .map(
            (item) => Candle.fromJson(Map<String, dynamic>.from(item as Map)),
          )
          .toList(),
      cursor = json['cursor'] as int,
      highWatermark = json['high_watermark'] as int,
      hasMore = json['has_more'] as bool,
      updatedAt = json['last_updated_at'] == null
          ? null
          : DateTime.parse(json['last_updated_at'] as String),
      marketData = MarketDataInfo.fromJson(
        Map<String, dynamic>.from(json['market_data'] as Map),
      ) {
    if (json['schema_version'] != '2.0' ||
        cursor < 0 ||
        highWatermark < cursor ||
        hasMore != (cursor < highWatermark) ||
        (candles.isNotEmpty && candles.last.sequence != cursor)) {
      throw const FormatException('Snapshot inválido');
    }
  }

  final String streamId;
  final String symbol, timeframe;
  final List<Candle> candles;
  final int cursor, highWatermark;
  final bool hasMore;
  final DateTime? updatedAt;
  final MarketDataInfo marketData;
}
