typedef Json = Map<String, dynamic>;

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
      regime = json['regime'] as String,
      symbol = json['symbol'] as String,
      timeframe = json['timeframe'] as String,
      provider = json['provider'] as String {
    final prices = [open, high, low, close].map(double.parse).toList();
    if (sequence < 1 ||
        volume < 0 ||
        !openTime.isUtc ||
        !closeTime.isUtc ||
        closeTime.difference(openTime) != const Duration(hours: 1) ||
        prices.any((value) => !value.isFinite || value <= 0) ||
        prices[1] < prices[0] ||
        prices[1] < prices[3] ||
        prices[2] > prices[0] ||
        prices[2] > prices[3]) {
      throw const FormatException('Candle inválido');
    }
  }

  final String id, streamId, open, high, low, close, regime, symbol, timeframe, provider;
  final int sequence, volume;
  final DateTime openTime, closeTime;
}

class MarketDataInfo {
  MarketDataInfo.fromJson(Json json)
    : state = json['state'] as String,
      provider = json['provider'] as String?,
      feed = json['feed'] as String?,
      symbols = (json['symbols'] as List?)?.cast<String>();

  final String state;
  final String? provider;
  final String? feed;
  final List<String>? symbols;
}

class Snapshot {
  Snapshot.fromJson(Json json)
    : streamId = json['stream_id'] as String,
      symbol = json['symbol'] as String?,
      timeframe = json['timeframe'] as String?,
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
        Map<String, dynamic>.from(json['simulator'] ?? json['market_data'] ?? {'state': 'offline'}),
      ) {
    if (json['schema_version'] != '1.0' ||
        cursor < 0 ||
        highWatermark < cursor ||
        hasMore != (cursor < highWatermark) ||
        (candles.isNotEmpty && candles.last.sequence != cursor)) {
      throw const FormatException('Snapshot inválido');
    }
  }

  final String streamId;
  final String? symbol, timeframe;
  final List<Candle> candles;
  final int cursor, highWatermark;
  final bool hasMore;
  final DateTime? updatedAt;
  final MarketDataInfo marketData;
}
