class BacktestMetrics {
  final String initialCash;
  final String finalEquity;
  final String returnPct;
  final String maxDrawdown;
  final String maxDrawdownPct;
  final int closedTrades;
  final int winningTrades;
  final int losingTrades;
  final String? winRatePct;
  final String? averageProfit;
  final String? averageLoss;
  final String? profitFactor;
  final String totalPnlNet;
  final String fees;
  final String slippage;
  final int openPositions;

  BacktestMetrics({
    required this.initialCash,
    required this.finalEquity,
    required this.returnPct,
    required this.maxDrawdown,
    required this.maxDrawdownPct,
    required this.closedTrades,
    required this.winningTrades,
    required this.losingTrades,
    this.winRatePct,
    this.averageProfit,
    this.averageLoss,
    this.profitFactor,
    required this.totalPnlNet,
    required this.fees,
    required this.slippage,
    required this.openPositions,
  });

  factory BacktestMetrics.fromJson(Map<String, dynamic> json) {
    return BacktestMetrics(
      initialCash: json['initial_cash'].toString(),
      finalEquity: json['final_equity'].toString(),
      returnPct: json['return_pct'].toString(),
      maxDrawdown: json['max_drawdown'].toString(),
      maxDrawdownPct: json['max_drawdown_pct'].toString(),
      closedTrades: json['closed_trades'] as int,
      winningTrades: json['winning_trades'] as int,
      losingTrades: json['losing_trades'] as int,
      winRatePct: json['win_rate_pct']?.toString(),
      averageProfit: json['average_profit']?.toString(),
      averageLoss: json['average_loss']?.toString(),
      profitFactor: json['profit_factor']?.toString(),
      totalPnlNet: json['total_pnl_net'].toString(),
      fees: json['fees'].toString(),
      slippage: json['slippage'].toString(),
      openPositions: json['open_positions'] as int,
    );
  }
}

class BacktestConfig {
  final String initialCash;
  final String feeBps;
  final String slippageBps;

  BacktestConfig({
    required this.initialCash,
    required this.feeBps,
    required this.slippageBps,
  });

  factory BacktestConfig.fromJson(Map<String, dynamic> json) {
    return BacktestConfig(
      initialCash: json['initial_cash'].toString(),
      feeBps: json['fee_bps'].toString(),
      slippageBps: json['slippage_bps'].toString(),
    );
  }
}

class BacktestSummary {
  final String resultHash;
  final String manifestHash;
  final String datasetHash;
  final String engineVersion;
  final String strategyVersion;
  final String riskVersion;
  final BacktestConfig config;
  final BacktestMetrics metrics;

  BacktestSummary({
    required this.resultHash,
    required this.manifestHash,
    required this.datasetHash,
    required this.engineVersion,
    required this.strategyVersion,
    required this.riskVersion,
    required this.config,
    required this.metrics,
  });

  factory BacktestSummary.fromJson(Map<String, dynamic> json) {
    return BacktestSummary(
      resultHash: json['result_hash'] as String,
      manifestHash: json['manifest_hash'] as String,
      datasetHash: json['dataset_hash'] as String,
      engineVersion: json['engine_version'] as String,
      strategyVersion: json['strategy_version'] as String,
      riskVersion: json['risk_version'] as String,
      config: BacktestConfig.fromJson(json['config'] as Map<String, dynamic>),
      metrics: BacktestMetrics.fromJson(json['metrics'] as Map<String, dynamic>),
    );
  }
}

class EquityFrame {
  final int step;
  final DateTime timestamp;
  final String equity;
  final String cash;
  final String marketValue;
  final String drawdown;

  EquityFrame({
    required this.step,
    required this.timestamp,
    required this.equity,
    required this.cash,
    required this.marketValue,
    required this.drawdown,
  });

  factory EquityFrame.fromJson(Map<String, dynamic> json) {
    return EquityFrame(
      step: json['step'] as int,
      timestamp: DateTime.parse(json['timestamp'] as String),
      equity: json['equity'].toString(),
      cash: json['cash'].toString(),
      marketValue: json['market_value'].toString(),
      drawdown: json['drawdown'].toString(),
    );
  }
}

class BacktestTrade {
  final String symbol;
  final String openedAt;
  final String closedAt;
  final int quantity;
  final String fees;
  final String netPnl;

  BacktestTrade({
    required this.symbol,
    required this.openedAt,
    required this.closedAt,
    required this.quantity,
    required this.fees,
    required this.netPnl,
  });

  factory BacktestTrade.fromJson(Map<String, dynamic> json) {
    return BacktestTrade(
      symbol: json['symbol'] as String,
      openedAt: json['opened_at'] as String,
      closedAt: json['closed_at'] as String,
      quantity: json['quantity'] as int,
      fees: json['fees'].toString(),
      netPnl: json['net_pnl'].toString(),
    );
  }
}

class BacktestOutcome {
  final String symbol;
  final DateTime executedAt;
  final String status;
  final String reason;
  final String referencePrice;
  final int quantity;

  BacktestOutcome({
    required this.symbol,
    required this.executedAt,
    required this.status,
    required this.reason,
    required this.referencePrice,
    required this.quantity,
  });

  factory BacktestOutcome.fromJson(Map<String, dynamic> json) {
    return BacktestOutcome(
      symbol: json['symbol'] as String,
      executedAt: DateTime.parse(json['executed_at'] as String),
      status: json['status'] as String,
      reason: json['reason'] as String,
      referencePrice: json['reference_price'].toString(),
      quantity: json['quantity'] as int,
    );
  }
}

class BacktestReport extends BacktestSummary {
  final List<EquityFrame> equityCurve;
  final List<BacktestTrade> trades;
  final List<BacktestOutcome> outcomes;

  BacktestReport({
    required super.resultHash,
    required super.manifestHash,
    required super.datasetHash,
    required super.engineVersion,
    required super.strategyVersion,
    required super.riskVersion,
    required super.config,
    required super.metrics,
    required this.equityCurve,
    required this.trades,
    required this.outcomes,
  });

  factory BacktestReport.fromJson(Map<String, dynamic> json) {
    final summary = BacktestSummary.fromJson(json);
    return BacktestReport(
      resultHash: summary.resultHash,
      manifestHash: summary.manifestHash,
      datasetHash: summary.datasetHash,
      engineVersion: summary.engineVersion,
      strategyVersion: summary.strategyVersion,
      riskVersion: summary.riskVersion,
      config: summary.config,
      metrics: summary.metrics,
      equityCurve: (json['equity_curve'] as List)
          .map((e) => EquityFrame.fromJson(e as Map<String, dynamic>))
          .toList(),
      trades: (json['trades'] as List)
          .map((e) => BacktestTrade.fromJson(e as Map<String, dynamic>))
          .toList(),
      outcomes: (json['outcomes'] as List)
          .map((e) => BacktestOutcome.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
