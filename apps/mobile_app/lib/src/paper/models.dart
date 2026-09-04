typedef Json = Map<String, dynamic>;

class PaperPortfolio {
  PaperPortfolio.fromJson(Json json)
      : runId = json['run_id'] as String?,
        status = json['status'] as String,
        provider = json['provider'] as String,
        paused = json['paused'] as bool,
        step = json['step'] as int,
        initialCash = double.parse(json['initial_cash'].toString()),
        cash = double.parse(json['cash'].toString()),
        marketValue = double.parse(json['market_value'].toString()),
        equity = double.parse(json['equity'].toString()),
        totalPnl = double.parse(json['total_pnl'].toString()),
        positions = (json['positions'] as List)
            .map((item) => PaperPosition.fromJson(item as Json))
            .toList();

  final String? runId;
  final String status;
  final String provider;
  final bool paused;
  final int step;
  final double initialCash;
  final double cash;
  final double marketValue;
  final double equity;
  final double totalPnl;
  final List<PaperPosition> positions;
}

class PaperPosition {
  PaperPosition.fromJson(Json json)
      : symbol = json['symbol'] as String,
        quantity = json['quantity'] as int,
        marketValue = double.parse(json['market_value'].toString()),
        unrealizedPnl = double.parse(json['unrealized_pnl'].toString());

  final String symbol;
  final int quantity;
  final double marketValue;
  final double unrealizedPnl;
}
