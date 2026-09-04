import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:async';
import 'api.dart';
import 'controller.dart';
import 'models.dart';
import 'chart.dart';
import '../market/chart.dart' show utcLabel;

class BacktestPage extends StatefulWidget {
  const BacktestPage({super.key, this.controller});

  final BacktestController? controller;

  @override
  State<BacktestPage> createState() => _BacktestPageState();
}

class _BacktestPageState extends State<BacktestPage> {
  late final BacktestController controller;

  @override
  void initState() {
    super.initState();
    controller =
        widget.controller ??
        BacktestController(
          api: HttpBacktestApi(const String.fromEnvironment('API_BASE_URL')),
        );
    if (widget.controller == null ||
        controller.listState == BacktestState.loading &&
            controller.summaries.isEmpty) {
      controller.loadSummaries();
    }
  }

  @override
  void dispose() {
    if (widget.controller == null) controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        if (controller.currentReport != null) {
          return BacktestDetailPage(controller: controller);
        }
        return Scaffold(
          appBar: AppBar(
            title: const Text('BACKTEST / HISTÓRICO'),
            backgroundColor: Colors.blueGrey[900],
          ),
          body: _buildList(),
        );
      },
    );
  }

  Widget _buildList() {
    if (controller.listState == BacktestState.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (controller.listState == BacktestState.error) {
      return Center(
        child: Text(controller.errorMessage ?? 'Erro desconhecido.'),
      );
    }
    if (controller.summaries.isEmpty) {
      return const Center(child: Text('Nenhum backtest encontrado.'));
    }
    return ListView.builder(
      itemCount: controller.summaries.length,
      itemBuilder: (context, index) {
        final summary = controller.summaries[index];
        final isProfit = double.parse(summary.metrics.returnPct) >= 0;
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: ListTile(
            title: Text('Retorno: ${summary.metrics.returnPct}%'),
            subtitle: Text(
              'Hash: ${summary.resultHash.length > 8 ? summary.resultHash.substring(0, 8) : summary.resultHash}...',
            ),
            trailing: Icon(
              isProfit ? Icons.trending_up : Icons.trending_down,
              color: isProfit ? Colors.green : Colors.red,
            ),
            onTap: () => controller.loadReport(summary.resultHash),
          ),
        );
      },
    );
  }
}

class BacktestDetailPage extends StatelessWidget {
  const BacktestDetailPage({super.key, required this.controller});
  final BacktestController controller;

  @override
  Widget build(BuildContext context) {
    final report = controller.currentReport!;
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('BACKTEST HISTÓRICO - DINHEIRO FICTÍCIO'),
          backgroundColor: Colors.blueGrey[900],
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () {
              controller.clearReport();
            },
          ),
          actions: [
            IconButton(
              tooltip: 'Exportar Relatório',
              icon: const Icon(Icons.download),
              onPressed: () async {
                final url = Uri.parse(
                  controller.api.getExportUrl(report.resultHash),
                );
                await launchUrl(url);
              },
            ),
          ],
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'Resumo'),
              Tab(text: 'Curva'),
              Tab(text: 'Trades'),
              Tab(text: 'Replay'),
            ],
          ),
        ),
        body: SafeArea(
          child: TabBarView(
            children: [
              _SummaryTab(report: report),
              _CurveTab(report: report),
              _TradesTab(report: report),
              _ReplayTab(controller: controller),
            ],
          ),
        ),
      ),
    );
  }
}

class _SummaryTab extends StatelessWidget {
  const _SummaryTab({required this.report});
  final BacktestReport report;

  @override
  Widget build(BuildContext context) {
    final isProfit = double.parse(report.metrics.totalPnlNet) >= 0;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.blueGrey[800],
            child: const Text(
              'ATENÇÃO: MODO BACKTEST.\nEste é um resultado histórico com dinheiro fictício. NÃO confunda com a simulação atual (PAPER).',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Métricas Financeiras',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 24,
            runSpacing: 16,
            children: [
              _MetricValue(
                'Retorno',
                '${report.metrics.returnPct}%',
                isProfit ? Colors.green : Colors.red,
              ),
              _MetricValue('Patrimônio final', report.metrics.finalEquity),
              _MetricValue(
                'P&L líquido',
                report.metrics.totalPnlNet,
                isProfit ? Colors.green : Colors.red,
              ),
              _MetricValue(
                'Drawdown máximo',
                report.metrics.maxDrawdown,
                Colors.red,
              ),
              _MetricValue(
                'Operações encerradas',
                '${report.metrics.closedTrades}',
              ),
              _MetricValue(
                'Win rate',
                report.metrics.winRatePct != null
                    ? '${report.metrics.winRatePct}%'
                    : 'N/A',
              ),
              _MetricValue(
                'Profit factor',
                report.metrics.profitFactor ?? 'N/A',
              ),
              _MetricValue(
                'Lucro médio',
                report.metrics.averageProfit ?? 'N/A',
                Colors.green,
              ),
              _MetricValue(
                'Perda média',
                report.metrics.averageLoss ?? 'N/A',
                Colors.red,
              ),
              _MetricValue('Fees', report.metrics.fees),
              _MetricValue('Slippage', report.metrics.slippage),
              _MetricValue(
                'Posições abertas ao fim',
                '${report.metrics.openPositions}',
              ),
            ],
          ),
          const Divider(height: 32),
          Text('Configuração', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Wrap(
            spacing: 24,
            runSpacing: 16,
            children: [
              _MetricValue('Dataset Hash', report.datasetHash.substring(0, 8)),
              _MetricValue(
                'Quantidade de frames',
                '${report.equityCurve.length}',
              ),
              _MetricValue('Strategy version', report.strategyVersion),
              _MetricValue('Risk version', report.riskVersion),
              _MetricValue('Engine version', report.engineVersion),
              _MetricValue('Fee bps', report.config.feeBps),
              _MetricValue('Slippage bps', report.config.slippageBps),
              _MetricValue('Capital inicial', report.config.initialCash),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricValue extends StatelessWidget {
  const _MetricValue(this.label, this.value, [this.color]);
  final String label, value;
  final Color? color;
  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: Theme.of(context).textTheme.bodySmall),
      Text(
        value,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          color: color,
          fontWeight: FontWeight.bold,
        ),
      ),
    ],
  );
}

class _CurveTab extends StatelessWidget {
  const _CurveTab({required this.report});
  final BacktestReport report;
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.blueGrey[800],
              width: double.infinity,
              child: const Text(
                'MODO BACKTEST - HISTÓRICO',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(height: 16),
            EquityCurveChart(curve: report.equityCurve),
          ],
        ),
      ),
    );
  }
}

class _TradesTab extends StatelessWidget {
  const _TradesTab({required this.report});
  final BacktestReport report;
  @override
  Widget build(BuildContext context) {
    if (report.trades.isEmpty) {
      return const Center(child: Text('Nenhum trade encerrado.'));
    }
    return ListView.builder(
      itemCount: report.trades.length,
      itemBuilder: (context, index) {
        final trade = report.trades[index];
        final pnl = double.parse(trade.netPnl);
        final color = pnl > 0
            ? Colors.green
            : (pnl < 0 ? Colors.red : Colors.grey);
        final result = pnl > 0 ? 'WIN' : (pnl < 0 ? 'LOSS' : 'BREAKEVEN');
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Flexible(
                      child: Text(
                        '${trade.symbol} - $result',
                        style: TextStyle(
                          color: color,
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                    ),
                    Flexible(
                      child: Text(
                        'P&L Líquido: ${trade.netPnl}',
                        style: TextStyle(
                          color: color,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ),
                const Divider(),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Flexible(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'BUY',
                            style: TextStyle(color: Colors.blue[300]),
                          ),
                          Text(utcLabel(DateTime.parse(trade.openedAt))),
                          Text('Qtd: ${trade.quantity}'),
                        ],
                      ),
                    ),
                    Flexible(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            'SELL',
                            style: TextStyle(color: Colors.purple[300]),
                          ),
                          Text(utcLabel(DateTime.parse(trade.closedAt))),
                          Text('Fees: ${trade.fees}'),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _ReplayTab extends StatefulWidget {
  const _ReplayTab({required this.controller});
  final BacktestController controller;
  @override
  State<_ReplayTab> createState() => _ReplayTabState();
}

class _ReplayTabState extends State<_ReplayTab> {
  Timer? _timer;
  bool _isPlaying = false;

  void _togglePlay() {
    if (_isPlaying) {
      _timer?.cancel();
    } else {
      _timer = Timer.periodic(const Duration(milliseconds: 500), (timer) {
        if (widget.controller.replayIndex <
            widget.controller.currentReport!.equityCurve.length - 1) {
          widget.controller.advanceReplay();
        } else {
          timer.cancel();
          setState(() {
            _isPlaying = false;
          });
        }
      });
    }
    setState(() {
      _isPlaying = !_isPlaying;
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
        final report = widget.controller.currentReport!;
        if (report.equityCurve.isEmpty) {
          return const Center(child: Text('Nenhum frame neste relatório.'));
        }
        final frame = report.equityCurve[widget.controller.replayIndex];

        // M4 frames are CLOSE snapshots of 1h bars; fills happen at their OPEN.
        final openedAt = frame.timestamp.subtract(const Duration(hours: 1));
        final outcomes = report.outcomes
            .where((o) => o.executedAt.isAtSameMomentAs(openedAt))
            .toList();

        return Column(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.blueGrey[800],
              width: double.infinity,
              child: const Text(
                'REPLAY VISUAL - BACKTEST',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    EquityCurveChart(
                      curve: report.equityCurve,
                      selectedIndex: widget.controller.replayIndex,
                      onSelect: (idx) {
                        _timer?.cancel();
                        setState(() => _isPlaying = false);
                        widget.controller.setReplayIndex(idx);
                      },
                    ),
                    const SizedBox(height: 16),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Estado',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const Divider(),
                            Wrap(
                              spacing: 24,
                              runSpacing: 12,
                              children: [
                                _MetricValue(
                                  'Timestamp',
                                  utcLabel(frame.timestamp),
                                ),
                                _MetricValue('Equity', frame.equity),
                                _MetricValue('Cash', frame.cash),
                                _MetricValue('Market Value', frame.marketValue),
                                _MetricValue('Drawdown', frame.drawdown),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    if (outcomes.isNotEmpty)
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Eventos neste candle',
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                              const Divider(),
                              ...outcomes.map(
                                (o) => ListTile(
                                  title: Text('${o.symbol} - ${o.status}'),
                                  subtitle: Text(
                                    'Reason: ${o.reason} | Price: ${o.referencePrice} | Qty: ${o.quantity}',
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Container(
              color: Theme.of(context).colorScheme.surfaceContainerHigh,
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    tooltip: 'Início',
                    icon: const Icon(Icons.skip_previous),
                    onPressed: widget.controller.replayIndex > 0
                        ? () {
                            _timer?.cancel();
                            setState(() => _isPlaying = false);
                            widget.controller.setReplayIndex(0);
                          }
                        : null,
                  ),
                  IconButton(
                    tooltip: 'Anterior',
                    icon: const Icon(Icons.fast_rewind),
                    onPressed: widget.controller.replayIndex > 0
                        ? () {
                            _timer?.cancel();
                            setState(() => _isPlaying = false);
                            widget.controller.rewindReplay();
                          }
                        : null,
                  ),
                  IconButton(
                    tooltip: _isPlaying ? 'Pausar replay' : 'Reproduzir replay',
                    icon: Icon(_isPlaying ? Icons.pause : Icons.play_arrow),
                    iconSize: 32,
                    onPressed: _togglePlay,
                  ),
                  IconButton(
                    tooltip: 'Próximo',
                    icon: const Icon(Icons.fast_forward),
                    onPressed:
                        widget.controller.replayIndex <
                            report.equityCurve.length - 1
                        ? () {
                            _timer?.cancel();
                            setState(() => _isPlaying = false);
                            widget.controller.advanceReplay();
                          }
                        : null,
                  ),
                  IconButton(
                    tooltip: 'Fim',
                    icon: const Icon(Icons.skip_next),
                    onPressed:
                        widget.controller.replayIndex <
                            report.equityCurve.length - 1
                        ? () {
                            _timer?.cancel();
                            setState(() => _isPlaying = false);
                            widget.controller.setReplayIndex(
                              report.equityCurve.length - 1,
                            );
                          }
                        : null,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}
