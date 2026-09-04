import '../market/models.dart';

class Decision {
  Decision.fromJson(Json json)
    : candle = Candle.fromJson(json['candle'] as Json),
      signalId = json['signal']['signal_id'] as String,
      type = json['signal']['signal_type'] as String,
      version = json['signal']['strategy_version'] as String,
      reason = json['signal']['reason'] as String,
      generatedAt = DateTime.parse(json['signal']['generated_at'] as String),
      riskId = json['risk']['decision_id'] as String,
      risk = json['risk']['decision'] as String,
      riskReason = json['risk']['reason'] as String,
      decidedAt = DateTime.parse(json['risk']['decided_at'] as String),
      paperStatus = json['paper'] != null ? json['paper']['status'] as String? : null {
    if (!['BUY', 'SELL', 'HOLD'].contains(type) ||
        !['APPROVED', 'REJECTED'].contains(risk) ||
        reason.trim().isEmpty ||
        version.isEmpty ||
        !generatedAt.isUtc ||
        !decidedAt.isUtc ||
        json['signal']['candle_id'] != candle.id ||
        json['signal']['stream_id'] != candle.streamId ||
        json['risk']['signal_id'] != signalId) {
      throw const FormatException('Decisão inválida');
    }
  }
  final Candle candle;
  final String signalId, type, version, reason, riskId, risk, riskReason;
  final DateTime generatedAt, decidedAt;
  final String? paperStatus;
}

class DecisionsSnapshot {
  DecisionsSnapshot.fromJson(Json json)
    : symbol = json['symbol'] as String,
      symbols = (json['symbols'] as List).cast<String>(),
      items = (json['items'] as List)
          .map((item) => Decision.fromJson(item as Json))
          .toList(),
      marketData = MarketDataInfo.fromJson(json['market_data'] as Json) {
    if (json['schema_version'] != '1.0' ||
        json['execution'] != 'NONE' && json['execution'] != 'LOCAL_PAPER' ||
        json['timeframe'] != '1h' ||
        !symbols.contains(symbol) ||
        items.any((item) => item.candle.symbol != symbol) ||
        items.map((item) => item.signalId).toSet().length != items.length) {
      throw const FormatException('Consulta de decisões inválida');
    }
    for (var i = 1; i < items.length; i++) {
      if (items[i].candle.openTime.isAfter(items[i - 1].candle.openTime)) {
        throw const FormatException('Decisões fora de ordem');
      }
    }
  }
  final String symbol;
  final List<String> symbols;
  final List<Decision> items;
  final MarketDataInfo marketData;
}
