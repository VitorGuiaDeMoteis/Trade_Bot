import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'models.dart';

String utcLabel(DateTime value) =>
    '${value.toUtc().toIso8601String().substring(0, 19).replaceFirst('T', ' ')} UTC';

class CandleChart extends StatefulWidget {
  const CandleChart({super.key, required this.candles});

  final List<Candle> candles;

  @override
  State<CandleChart> createState() => _CandleChartState();
}

class _CandleChartState extends State<CandleChart> {
  String? selectedId;

  @override
  Widget build(BuildContext context) {
    final visible = widget.candles
        .skip(math.max(0, widget.candles.length - 60))
        .toList();

    var selected = visible.indexWhere((c) => c.id == selectedId);

    if (selected < 0) selected = visible.length - 1;

    final candle = visible[selected];

    final colors = Theme.of(context).colorScheme;

    final minimum = visible.map((c) => double.parse(c.low)).reduce(math.min);

    final maximum = visible.map((c) => double.parse(c.high)).reduce(math.max);

    final regime = switch (candle.regime) {
      'uptrend' => 'Alta',

      'downtrend' => 'Baixa',

      'sideways' => 'Lateralização',

      'volatile' => 'Maior volatilidade',

      _ => candle.regime ?? 'Não classificado',
    };

    void select(int index) => setState(() {
      selectedId = index == visible.length - 1 ? null : visible[index].id;
    });

    return Card(
      margin: EdgeInsets.zero,

      child: Padding(
        padding: const EdgeInsets.all(16),

        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,

          children: [
            Text(
              'Candles · últimos ${visible.length}',

              style: Theme.of(context).textTheme.titleMedium,
            ),

            const SizedBox(height: 4),

            const Text('Toque no gráfico ou use as setas para inspecionar.'),

            const SizedBox(height: 16),

            Text(
              'Faixa ${minimum.toStringAsFixed(4)} – ${maximum.toStringAsFixed(4)}',
            ),

            const SizedBox(height: 8),

            // Valores decimais são convertidos apenas em coordenadas de desenho.

            // O painel de inspeção usa as strings originais do contrato.
            LayoutBuilder(
              builder: (context, constraints) {
                return Semantics(
                  label:
                      'Gráfico de ${visible.length} candles. Inspeção disponível nos botões anterior e próximo.',

                  image: true,

                  child: GestureDetector(
                    excludeFromSemantics: true,

                    key: const Key('candle-chart'),

                    onTapDown: (details) {
                      final fraction =
                          ((details.localPosition.dx - 4) /
                                  (constraints.maxWidth - 8))
                              .clamp(0.0, 0.999999);

                      select((fraction * visible.length).floor());
                    },

                    child: RepaintBoundary(
                      child: SizedBox(
                        width: double.infinity,

                        height: 240,

                        child: CustomPaint(
                          painter: _CandlesPainter(
                            candles: visible,

                            selected: selected,

                            grid: colors.outlineVariant,

                            line: colors.onSurface,
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),

            const SizedBox(height: 8),

            Wrap(
              spacing: 16,

              runSpacing: 6,

              children: [
                Text('De ${utcLabel(visible.first.openTime)}'),

                Text('até ${utcLabel(visible.last.closeTime)}'),
              ],
            ),

            const Divider(height: 28),

            Wrap(
              spacing: 12,

              runSpacing: 8,

              crossAxisAlignment: WrapCrossAlignment.center,

              children: [
                IconButton.filledTonal(
                  key: const Key('previous-candle'),

                  tooltip: 'Candle anterior',

                  constraints: const BoxConstraints(
                    minWidth: 48,

                    minHeight: 48,
                  ),

                  onPressed: selected > 0 ? () => select(selected - 1) : null,

                  icon: const Icon(Icons.chevron_left),
                ),

                Text(
                  'Candle #${candle.sequence}',

                  key: const Key('selected-candle'),

                  style: Theme.of(context).textTheme.titleMedium,
                ),

                IconButton.filledTonal(
                  key: const Key('next-candle'),

                  tooltip: 'Próximo candle',

                  constraints: const BoxConstraints(
                    minWidth: 48,

                    minHeight: 48,
                  ),

                  onPressed: selected < visible.length - 1
                      ? () => select(selected + 1)
                      : null,

                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),

            const SizedBox(height: 12),

            Text(
              '${candle.provider == 'simulator' ? 'Fechamento virtual' : 'Fechamento'}: ${utcLabel(candle.closeTime)}',
            ),

            const SizedBox(height: 12),

            Wrap(
              spacing: 24,

              runSpacing: 12,

              children: [
                _Value('Abertura', candle.open),

                _Value('Máxima', candle.high),

                _Value('Mínima', candle.low),

                _Value('Fechamento', candle.close),

                _Value('Volume', candle.volume.toString()),

                if (candle.provider == 'simulator')
                  _Value('Regime simulado', regime),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Value extends StatelessWidget {
  const _Value(this.label, this.value);

  final String label, value;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,

    children: [
      Text(label, style: Theme.of(context).textTheme.bodySmall),

      Text(value, style: Theme.of(context).textTheme.titleSmall),
    ],
  );
}

class _CandlesPainter extends CustomPainter {
  const _CandlesPainter({
    required this.candles,

    required this.selected,

    required this.grid,

    required this.line,
  });

  final List<Candle> candles;

  final int selected;

  final Color grid, line;

  @override
  void paint(Canvas canvas, Size size) {
    final minimum = candles.map((c) => double.parse(c.low)).reduce(math.min);

    final maximum = candles.map((c) => double.parse(c.high)).reduce(math.max);

    final spread = math.max(maximum - minimum, 0.0001);

    const top = 8.0;

    final height = size.height - top - 8;

    double y(double value) => top + (maximum - value) / spread * height;

    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;

    for (var i = 0; i <= 4; i++) {
      final position = top + height * i / 4;

      canvas.drawLine(
        Offset(0, position),

        Offset(size.width, position),

        gridPaint,
      );
    }

    final step = (size.width - 8) / candles.length;

    for (var i = 0; i < candles.length; i++) {
      final candle = candles[i];

      final x = 4 + step * (i + 0.5);

      final open = double.parse(candle.open),
          close = double.parse(candle.close);

      final paint = Paint()
        ..color = close >= open
            ? const Color(0xFF9DBDFF)
            : const Color(0xFFD0B5FF)
        ..strokeWidth = 1.5;

      canvas.drawLine(
        Offset(x, y(double.parse(candle.high))),

        Offset(x, y(double.parse(candle.low))),

        paint,
      );

      final bodyTop = math.min(y(open), y(close));

      canvas.drawRect(
        Rect.fromLTWH(
          x - step * 0.3,

          bodyTop,

          math.max(step * 0.6, 1),

          math.max((y(open) - y(close)).abs(), 1.5),
        ),

        paint,
      );

      if (i == selected) {
        canvas.drawLine(
          Offset(x, top),

          Offset(x, size.height),

          Paint()
            ..color = line.withValues(alpha: 0.45)
            ..strokeWidth = 1,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_CandlesPainter oldDelegate) =>
      !identical(candles, oldDelegate.candles) ||
      selected != oldDelegate.selected ||
      grid != oldDelegate.grid ||
      line != oldDelegate.line;
}
