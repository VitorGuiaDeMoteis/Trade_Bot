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
    return Scaffold(
      appBar: AppBar(
        title: const Text('CARTEIRA SIMULADA', style: TextStyle(color: Colors.orange)),
        backgroundColor: Colors.orange.withAlpha(25),
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
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                color: Colors.orange.withAlpha(25),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Status: ${p.status}', style: const TextStyle(fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      Text('Equity: \$${p.equity.toStringAsFixed(2)}', style: const TextStyle(fontSize: 24)),
                      Text('Cash: \$${p.cash.toStringAsFixed(2)}'),
                      Text('Market Value: \$${p.marketValue.toStringAsFixed(2)}'),
                      Text('Total PnL: \$${p.totalPnl.toStringAsFixed(2)}', 
                        style: TextStyle(color: p.totalPnl >= 0 ? Colors.green : Colors.red)),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text('Posicoes', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              if (p.positions.isEmpty) const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Nenhuma posicao aberta.'),
              ),
              for (final pos in p.positions)
                ListTile(
                  title: Text(pos.symbol),
                  subtitle: Text('${pos.quantity} shares'),
                  trailing: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text('\$${pos.marketValue.toStringAsFixed(2)}'),
                      Text('\$${pos.unrealizedPnl.toStringAsFixed(2)}',
                        style: TextStyle(color: pos.unrealizedPnl >= 0 ? Colors.green : Colors.red)),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
