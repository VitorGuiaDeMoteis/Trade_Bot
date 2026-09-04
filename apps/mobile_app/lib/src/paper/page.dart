import 'package:flutter/material.dart';
import 'controller.dart';

class PaperPage extends StatefulWidget {
  const PaperPage({super.key, required this.controller});
  final PaperController controller;

  @override
  State<PaperPage> createState() => _PaperPageState();
}

class _PaperPageState extends State<PaperPage> {
  @override
  void initState() {
    super.initState();
    widget.controller.loadPortfolio();
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('CARTEIRA SIMULADA', style: TextStyle(color: Colors.orange)),
          backgroundColor: Colors.orange.withAlpha(25),
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: widget.controller.loadPortfolio,
            )
          ],
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'Summary'),
              Tab(text: 'Positions'),
              Tab(text: 'Orders'),
              Tab(text: 'Fills'),
            ],
          ),
        ),
        body: ListenableBuilder(
          listenable: widget.controller,
          builder: (context, _) {
            if (widget.controller.isLoading) {
              return const Center(child: CircularProgressIndicator());
            }
            if (widget.controller.error != null) {
              return Center(child: Text(widget.controller.error!, style: const TextStyle(color: Colors.red)));
            }
            final p = widget.controller.portfolio;
            if (p == null) {
              return const Center(child: Text('Nenhuma simulacao ativa.'));
            }
            return TabBarView(
              children: [
                // Summary
                ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Card(
                      color: Colors.orange.withAlpha(25),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Status: ${p.status}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                            const SizedBox(height: 8),
                            Text('Equity: \$${p.equity.toStringAsFixed(2)}', style: const TextStyle(fontSize: 24)),
                            Text('Cash: \$${p.cash.toStringAsFixed(2)}'),
                            Text('Market Value: \$${p.marketValue.toStringAsFixed(2)}'),
                            Text('Unrealized PnL: \$${p.unrealizedPnl.toStringAsFixed(2)}', style: TextStyle(color: p.unrealizedPnl >= 0 ? Colors.green : Colors.red)),
                            Text('Realized PnL: \$${p.realizedPnl.toStringAsFixed(2)}', style: TextStyle(color: p.realizedPnl >= 0 ? Colors.green : Colors.red)),
                            Text('Total PnL: \$${p.totalPnl.toStringAsFixed(2)}', style: TextStyle(color: p.totalPnl >= 0 ? Colors.green : Colors.red)),
                            Text('Fees: \$${p.fees.toStringAsFixed(2)}', style: const TextStyle(color: Colors.red)),
                            const SizedBox(height: 16),
                            Row(
                              children: [
                                Text('Paused: ${p.paused ? 'YES' : 'NO'}', style: const TextStyle(fontWeight: FontWeight.bold)),
                                const Spacer(),
                                FilledButton(
                                  onPressed: () => widget.controller.togglePause(!p.paused),
                                  child: Text(p.paused ? 'RESUME' : 'PAUSE'),
                                )
                              ],
                            )
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                // Positions
                p.positions.isEmpty
                    ? const Center(child: Text('Nenhuma posicao.'))
                    : ListView.builder(
                        itemCount: p.positions.length,
                        itemBuilder: (context, index) {
                          final pos = p.positions[index];
                          return ListTile(
                            title: Text(pos.symbol),
                            subtitle: Text('${pos.quantity} shares'),
                            trailing: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text('\$${pos.marketValue.toStringAsFixed(2)}'),
                                Text('\$${pos.unrealizedPnl.toStringAsFixed(2)}', style: TextStyle(color: pos.unrealizedPnl >= 0 ? Colors.green : Colors.red)),
                              ],
                            ),
                          );
                        },
                      ),
                // Orders
                p.orders.isEmpty
                    ? const Center(child: Text('Nenhuma ordem.'))
                    : ListView.builder(
                        itemCount: p.orders.length,
                        itemBuilder: (context, index) {
                          final ord = p.orders[index];
                          return ListTile(
                            title: Text('${ord.side} ${ord.quantity} ${ord.symbol}'),
                            subtitle: Text(ord.reason),
                            trailing: Text(ord.status, style: TextStyle(color: ord.status == 'FILLED' ? Colors.green : Colors.grey)),
                          );
                        },
                      ),
                // Fills
                p.fills.isEmpty
                    ? const Center(child: Text('Nenhum fill.'))
                    : ListView.builder(
                        itemCount: p.fills.length,
                        itemBuilder: (context, index) {
                          final fill = p.fills[index];
                          return ListTile(
                            title: Text('Fill ${fill.quantity} @ \$${fill.price.toStringAsFixed(2)}'),
                            subtitle: Text('Fee: \$${fill.fee.toStringAsFixed(2)} | PnL: \$${fill.realizedPnl.toStringAsFixed(2)}'),
                          );
                        },
                      ),
              ],
            );
          },
        ),
      ),
    );
  }
}
