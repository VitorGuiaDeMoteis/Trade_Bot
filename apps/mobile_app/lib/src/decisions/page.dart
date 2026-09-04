import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'controller.dart';
import 'models.dart';

String decisionUtc(DateTime time) =>
    '${time.toUtc().toIso8601String().substring(0, 19).replaceFirst('T', ' ')} UTC';

Color signalColor(String type) => switch (type) {
  'BUY' => const Color(0xFF81C995),
  'SELL' => const Color(0xFFFF9B9B),
  _ => const Color(0xFFE9C46A),
};

String sourceLabel(DecisionsSnapshot? snapshot) {
  final info = snapshot?.marketData;
  if (info == null) return 'AGUARDANDO FONTE';
  if (info.provider == 'simulator') return 'SIMULADO';
  return 'DADOS REAIS · ${info.provider?.toUpperCase()} / ${info.feed?.toUpperCase() ?? 'NÃO INFORMADO'}';
}

class DecisionsPage extends StatefulWidget {
  const DecisionsPage({super.key, this.controller});
  final DecisionsController? controller;
  @override
  State<DecisionsPage> createState() => _DecisionsPageState();
}

class _DecisionsPageState extends State<DecisionsPage> {
  late final DecisionsController controller;
  @override
  void initState() {
    super.initState();
    controller =
        widget.controller ??
        DecisionsController(
          api: HttpDecisionsApi(const String.fromEnvironment('API_BASE_URL')),
        );
    unawaited(controller.refresh());
  }

  @override
  void dispose() {
    if (widget.controller == null) controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('DECISÕES')),
    body: SafeArea(
      child: ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          final snapshot = controller.snapshot;
          final items = snapshot?.items ?? <Decision>[];
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1000),
              child: ListView.builder(
                key: ValueKey('decisions-${controller.selectedSymbol}'),
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                itemCount: items.length + 1,
                itemBuilder: (context, index) {
                  if (index == 0) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Estratégia & risco',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                        const SizedBox(height: 8),
                        Text(sourceLabel(snapshot)),
                        const Text(
                          'Histórico persistido · 1h · horários em UTC',
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Decisões hipotéticas. Nenhuma ordem é criada ou enviada.',
                        ),
                        const SizedBox(height: 16),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final symbol in controller.symbols)
                              ConstrainedBox(
                                constraints: const BoxConstraints(
                                  minWidth: 64,
                                  minHeight: 48,
                                ),
                                child: ChoiceChip(
                                  key: Key('select-$symbol'),
                                  label: Text(symbol),
                                  selected: controller.selectedSymbol == symbol,
                                  onSelected: (_) => controller.select(symbol),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Text(
                          '${controller.selectedSymbol ?? '—'} · últimas ${items.length} decisões',
                          key: const Key('decisions-count'),
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 16,
                          runSpacing: 8,
                          children: [
                            for (final type in ['BUY', 'SELL', 'HOLD'])
                              Text(
                                '$type  ${items.where((i) => i.type == type).length}',
                                style: TextStyle(
                                  color: signalColor(type),
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        FilledButton.tonalIcon(
                          key: const Key('refresh-decisions'),
                          onPressed: controller.loading
                              ? null
                              : controller.refresh,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Atualizar consulta'),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'Até 50 registros · mais recentes primeiro · atualização manual',
                        ),
                        if (controller.loading) ...[
                          const SizedBox(height: 16),
                          const LinearProgressIndicator(),
                          const Text('Carregando decisões…'),
                        ],
                        if (controller.message != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            controller.message!,
                            semanticsLabel: controller.message,
                          ),
                          if (snapshot != null)
                            const Text(
                              'Última consulta exibida; atualização pendente.',
                            ),
                        ],
                        if (!controller.loading &&
                            controller.message == null &&
                            items.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: Text(
                              'Nenhuma decisão persistida para este ativo.',
                            ),
                          ),
                        const SizedBox(height: 16),
                      ],
                    );
                  }
                  final item = items[index - 1];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 14),
                    clipBehavior: Clip.antiAlias,
                    child: Semantics(
                      button: true,
                      child: InkWell(
                        key: Key('decision-${item.signalId}'),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => DecisionDetail(
                              item: item,
                              source: sourceLabel(snapshot),
                            ),
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${item.candle.symbol} · ${decisionUtc(item.candle.openTime)}',
                              ),
                              const SizedBox(height: 12),
                              Text(
                                item.type == 'HOLD'
                                    ? 'HOLD · SEM AÇÃO'
                                    : item.type,
                                key: Key('decision-type-${item.signalId}'),
                                style: Theme.of(context).textTheme.headlineSmall
                                    ?.copyWith(
                                      color: signalColor(item.type),
                                      fontWeight: FontWeight.bold,
                                    ),
                              ),
                              const SizedBox(height: 8),
                              Text('Estratégia · ${item.version}'),
                              Text(item.reason),
                              const SizedBox(height: 12),
                              _Risk(item: item),
              const SizedBox(height: 12),
              _Paper(item: item),
                              const SizedBox(height: 12),
                              const Text('Ver candle e detalhes →'),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          );
        },
      ),
    ),
  );
}


class _Paper extends StatelessWidget {
  const _Paper({required this.item});
  final Decision item;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        'Paper Execution  ${item.paperStatus ?? "WAITING"}',
        style: TextStyle(
          color: item.paperStatus == 'FILLED'
              ? const Color(0xFF81C995)
              : (item.paperStatus == 'WAITING' ? Colors.orange : const Color(0xFFFF9B9B)),
          fontWeight: FontWeight.bold,
        ),
      ),
    ],
  );
}

class _Risk extends StatelessWidget {
  const _Risk({required this.item});
  final Decision item;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        'Risco · ${item.risk}',
        style: TextStyle(
          color: item.risk == 'APPROVED'
              ? const Color(0xFF81C995)
              : const Color(0xFFFF9B9B),
          fontWeight: FontWeight.bold,
        ),
      ),
      Text(item.riskReason),
      if (item.type == 'HOLD')
        const Text('SEM AÇÃO · nenhuma operação seria executada.'),
    ],
  );
}

class DecisionDetail extends StatelessWidget {
  const DecisionDetail({super.key, required this.item, required this.source});
  final Decision item;
  final String source;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Detalhe da decisão')),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1000),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                item.candle.symbol,
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              Text('Candle fechado · ${item.candle.timeframe}'),
              Text('Abertura: ${decisionUtc(item.candle.openTime)}'),
              Text('Fechamento: ${decisionUtc(item.candle.closeTime)}'),
              const SizedBox(height: 20),
              for (final field in {
                'OPEN': item.candle.open,
                'HIGH': item.candle.high,
                'LOW': item.candle.low,
                'CLOSE': item.candle.close,
                'VOLUME': '${item.candle.volume}',
              }.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text('${field.key}    ${field.value}'),
                ),
              const Divider(height: 32),
              Text('Estratégia · ${item.version}'),
              Text(
                item.type == 'HOLD' ? 'HOLD · SEM AÇÃO' : item.type,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: signalColor(item.type),
                ),
              ),
              Text(item.reason),
              Text('Sinal gerado: ${decisionUtc(item.generatedAt)}'),
              const SizedBox(height: 20),
              _Risk(item: item),
              const SizedBox(height: 12),
              _Paper(item: item),
              Text('Avaliado: ${decisionUtc(item.decidedAt)}'),
              const Text(
                'Resultado histórico, sem reavaliação durante a consulta.',
              ),
              const Divider(height: 32),
              Text('Fonte do candle: ${item.candle.provider.toUpperCase()}'),
              Text(source),
              const Text(
                'Feed informado é a configuração atual do backend; não é um atributo histórico do candle.',
              ),
              const SizedBox(height: 20),
              const Text('EXECUÇÃO · NENHUMA ORDEM ENVIADA'),
              const Text(
                'Observação hipotética; não existe execução nesta etapa.',
              ),
              const SizedBox(height: 20),
              Text('Candle ID: ${item.candle.id}'),
              Text('Signal ID: ${item.signalId}'),
              Text('Risk ID: ${item.riskId}'),
            ],
          ),
        ),
      ),
    ),
  );
}
