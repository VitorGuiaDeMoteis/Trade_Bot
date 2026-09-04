import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../format.dart';
import '../models.dart';

class ChartPanel extends StatelessWidget {
  const ChartPanel({
    super.key,
    required this.symbol,
    required this.operationalTimeframe,
    required this.selectedTimeframe,
    required this.onTimeframeSelected,
    this.candles,
    this.loading = false,
  });

  final String symbol;
  final String operationalTimeframe;
  final ChartTimeframe selectedTimeframe;
  final ValueChanged<ChartTimeframe> onTimeframeSelected;
  final LiveCandlesResponse? candles;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('chart-panel'),
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHigh.withValues(
          alpha: 0.45,
        ),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: Theme.of(context).colorScheme.outlineVariant.withValues(
            alpha: 0.35,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                symbol,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              ...ChartTimeframe.values.map((tf) {
                final selected = tf == selectedTimeframe;
                final isOperational = tf.apiValue == operationalTimeframe;
                return FilterChip(
                  key: Key('tf-${tf.apiValue}'),
                  selected: selected,
                  label: Text(
                    isOperational ? '${tf.label} · STRATEGY' : tf.label,
                  ),
                  onSelected: (_) => onTimeframeSelected(tf),
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                );
              }),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Seletor altera só a visualização. Strategy permanece em $operationalTimeframe.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          if (loading && candles == null)
            const SizedBox(
              height: 220,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (candles == null || candles!.candles.isEmpty)
            const SizedBox(
              height: 180,
              child: Center(child: Text('Sem candles para este timeframe')),
            )
          else
            LiveCandleChart(
              candles: candles!.candles,
              markers: candles!.markers,
            ),
        ],
      ),
    );
  }
}

class LiveCandleChart extends StatefulWidget {
  const LiveCandleChart({
    super.key,
    required this.candles,
    this.markers = const [],
  });

  final List<LiveCandle> candles;
  final List<ChartMarker> markers;

  @override
  State<LiveCandleChart> createState() => _LiveCandleChartState();
}

class _LiveCandleChartState extends State<LiveCandleChart> {
  int? selected;

  @override
  Widget build(BuildContext context) {
    final visible = widget.candles.length > 80
        ? widget.candles.sublist(widget.candles.length - 80)
        : widget.candles;
    final index = (selected ?? visible.length - 1).clamp(0, visible.length - 1);
    final candle = visible[index];
    final colors = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LayoutBuilder(
          builder: (context, constraints) {
            return GestureDetector(
              key: const Key('live-candle-chart'),
              onTapDown: (details) {
                final fraction =
                    ((details.localPosition.dx - 4) /
                            (constraints.maxWidth - 8))
                        .clamp(0.0, 0.999999);
                setState(() => selected = (fraction * visible.length).floor());
              },
              child: SizedBox(
                width: double.infinity,
                height: 220,
                child: CustomPaint(
                  painter: _LiveCandlesPainter(
                    candles: visible,
                    markers: widget.markers,
                    selected: index,
                    grid: colors.outlineVariant,
                    line: colors.onSurface,
                  ),
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 16,
          runSpacing: 4,
          children: [
            Text(clockLabel(candle.openTime)),
            Text('O ${candle.open}'),
            Text('H ${candle.high}'),
            Text('L ${candle.low}'),
            Text('C ${candle.close}'),
          ],
        ),
        if (widget.markers.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Wrap(
              spacing: 12,
              children: const [
                Text('BUY ●', style: TextStyle(color: Color(0xFF3DDC97))),
                Text('SELL ●', style: TextStyle(color: Color(0xFFFF6B6B))),
              ],
            ),
          ),
      ],
    );
  }
}

class _LiveCandlesPainter extends CustomPainter {
  _LiveCandlesPainter({
    required this.candles,
    required this.markers,
    required this.selected,
    required this.grid,
    required this.line,
  });

  final List<LiveCandle> candles;
  final List<ChartMarker> markers;
  final int selected;
  final Color grid;
  final Color line;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty) return;
    final lows = candles.map((c) => double.tryParse(c.low) ?? 0).toList();
    final highs = candles.map((c) => double.tryParse(c.high) ?? 0).toList();
    final minimum = lows.reduce(math.min);
    final maximum = highs.reduce(math.max);
    final spread = math.max(maximum - minimum, 0.0001);
    const top = 8.0;
    final height = size.height - top - 8;
    double y(double value) => top + (maximum - value) / spread * height;

    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (var i = 0; i <= 4; i++) {
      final position = top + height * i / 4;
      canvas.drawLine(Offset(0, position), Offset(size.width, position), gridPaint);
    }

    final step = (size.width - 8) / candles.length;
    for (var i = 0; i < candles.length; i++) {
      final candle = candles[i];
      final x = 4 + step * (i + 0.5);
      final open = double.tryParse(candle.open) ?? 0;
      final close = double.tryParse(candle.close) ?? 0;
      final paint = Paint()
        ..color = close >= open
            ? const Color(0xFF7AA2FF)
            : const Color(0xFFB8A4D9)
        ..strokeWidth = 1.4;
      canvas.drawLine(
        Offset(x, y(double.tryParse(candle.high) ?? close)),
        Offset(x, y(double.tryParse(candle.low) ?? open)),
        paint,
      );
      final bodyTop = math.min(y(open), y(close));
      canvas.drawRect(
        Rect.fromLTWH(
          x - step * 0.28,
          bodyTop,
          math.max(step * 0.56, 1),
          math.max((y(open) - y(close)).abs(), 1.5),
        ),
        paint,
      );
      if (i == selected) {
        canvas.drawLine(
          Offset(x, top),
          Offset(x, size.height),
          Paint()
            ..color = line.withValues(alpha: 0.4)
            ..strokeWidth = 1,
        );
      }
    }

    // Markers: only when provided (never invent).
    for (final marker in markers) {
      final idx = _nearestIndex(marker.time);
      if (idx < 0) continue;
      final x = 4 + step * (idx + 0.5);
      final price =
          double.tryParse(marker.price ?? candles[idx].close) ??
          double.tryParse(candles[idx].close) ??
          0;
      final buy = marker.side.toUpperCase() == 'BUY';
      final paint = Paint()
        ..color = buy ? const Color(0xFF3DDC97) : const Color(0xFFFF6B6B);
      canvas.drawCircle(Offset(x, y(price)), 4.5, paint);
    }
  }

  int _nearestIndex(DateTime time) {
    if (candles.isEmpty) return -1;
    var best = 0;
    var bestDelta = candles.first.closeTime.difference(time).abs();
    for (var i = 1; i < candles.length; i++) {
      final delta = candles[i].closeTime.difference(time).abs();
      if (delta < bestDelta) {
        best = i;
        bestDelta = delta;
      }
    }
    return best;
  }

  @override
  bool shouldRepaint(covariant _LiveCandlesPainter oldDelegate) =>
      !identical(candles, oldDelegate.candles) ||
      !identical(markers, oldDelegate.markers) ||
      selected != oldDelegate.selected;
}
