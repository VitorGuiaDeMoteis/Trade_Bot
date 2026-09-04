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
        unrealizedPnl = double.parse(json['unrealized_pnl'].toString()),
        realizedPnl = double.parse(json['realized_pnl'].toString()),
        fees = double.parse(json['fees'].toString()),
        positions = (json['positions'] as List)
            .map((item) => PaperPosition.fromJson(item as Json))
            .toList(),
        orders = (json['orders'] as List).map((item) => PaperOrder.fromJson(item as Json)).toList(),
        fills = (json['fills'] as List).map((item) => PaperFill.fromJson(item as Json)).toList();

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
  final double unrealizedPnl;
  final double realizedPnl;
  final double fees;
  final List<PaperPosition> positions;
  final List<PaperOrder> orders;
  final List<PaperFill> fills;
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

class PaperOrder {
  PaperOrder.fromJson(Json json)
      : orderId = json['order_id'] as String,
        symbol = json['symbol'] as String,
        side = json['side'] as String,
        quantity = json['quantity'] as int,
        status = json['status'] as String,
        requestedAt = DateTime.parse(json['requested_at'] as String),
        reason = json['reason'] as String;

  final String orderId;
  final String symbol;
  final String side;
  final int quantity;
  final String status;
  final DateTime requestedAt;
  final String reason;
}

class PaperFill {
  PaperFill.fromJson(Json json)
      : fillId = json['fill_id'] as String,
        orderId = json['order_id'] as String,
        price = double.parse(json['price'].toString()),
        quantity = json['quantity'] as int,
        fee = double.parse(json['fee'].toString()),
        realizedPnl = double.parse(json['realized_pnl'].toString()),
        filledAt = DateTime.parse(json['filled_at'] as String);

  final String fillId;
  final String orderId;
  final double price;
  final int quantity;
  final double fee;
  final double realizedPnl;
  final DateTime filledAt;
}
