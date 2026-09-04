import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'models.dart';
import '../market/chart.dart'; // for utcLabel

class EquityCurveChart extends StatefulWidget {
  const EquityCurveChart({
    super.key,
    required this.curve,
    this.selectedIndex,
    this.onSelect,
  });

  final List<EquityFrame> curve;
  final int? selectedIndex;
  final ValueChanged<int>? onSelect;

  @override
  State<EquityCurveChart> createState() => _EquityCurveChartState();
}

class _EquityCurveChartState extends State<EquityCurveChart> {
  int? localSelected;

  int get selected =>
      widget.selectedIndex ?? localSelected ?? (widget.curve.length - 1);

  @override
  Widget build(BuildContext context) {
    if (widget.curve.isEmpty) return const SizedBox();

    final frame = widget.curve[selected.clamp(0, widget.curve.length - 1)];
    final colors = Theme.of(context).colorScheme;
    final minimum = widget.curve
        .map((c) => double.parse(c.equity))
        .reduce(math.min);
    final maximum = widget.curve
        .map((c) => double.parse(c.equity))
        .reduce(math.max);

    void select(int index) {
      if (widget.onSelect != null) {
        widget.onSelect!(index);
      } else {
        setState(() {
          localSelected = index;
        });
      }
    }

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Curva de Patrimônio',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'Faixa ${minimum.toStringAsFixed(2)} – ${maximum.toStringAsFixed(2)}',
            ),
            const SizedBox(height: 16),
            LayoutBuilder(
              builder: (context, constraints) {
                return GestureDetector(
                  onTapDown: (details) {
                    final fraction =
                        ((details.localPosition.dx - 4) /
                                (constraints.maxWidth - 8))
                            .clamp(0.0, 0.999999);
                    select((fraction * widget.curve.length).floor());
                  },
                  onHorizontalDragUpdate: (details) {
                    final fraction =
                        ((details.localPosition.dx - 4) /
                                (constraints.maxWidth - 8))
                            .clamp(0.0, 0.999999);
                    select((fraction * widget.curve.length).floor());
                  },
                  child: RepaintBoundary(
                    child: SizedBox(
                      width: constraints.maxWidth,
                      height: 240,
                      child: CustomPaint(
                        painter: _EquityPainter(
                          curve: widget.curve,
                          selected: selected,
                          grid: colors.outlineVariant,
                          line: colors.primary,
                          drawdownColor: Colors.red.withValues(alpha: 0.3),
                          cursor: colors.onSurface,
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 24,
              runSpacing: 12,
              children: [
                _Value('Passo', '#${frame.step}'),
                _Value('Data', utcLabel(frame.timestamp)),
                _Value('Patrimônio', frame.equity),
                _Value('Caixa', frame.cash),
                _Value(
                  'Drawdown',
                  frame.drawdown,
                  color: double.parse(frame.drawdown) > 0 ? Colors.red : null,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Value extends StatelessWidget {
  const _Value(this.label, this.value, {this.color});
  final String label, value;
  final Color? color;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: Theme.of(context).textTheme.bodySmall),
      Text(
        value,
        style: Theme.of(context).textTheme.titleSmall?.copyWith(color: color),
      ),
    ],
  );
}

class _EquityPainter extends CustomPainter {
  const _EquityPainter({
    required this.curve,
    required this.selected,
    required this.grid,
    required this.line,
    required this.drawdownColor,
    required this.cursor,
  });

  final List<EquityFrame> curve;
  final int selected;
  final Color grid, line, drawdownColor, cursor;

  @override
  void paint(Canvas canvas, Size size) {
    if (curve.isEmpty) return;

    final minimum = curve.map((c) => double.parse(c.equity)).reduce(math.min);
    // Monetary drawdown comes from the report; addition only maps its visual endpoint.
    final maximum = curve
        .map((c) => double.parse(c.equity) + double.parse(c.drawdown))
        .reduce(math.max);
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

    final step = (size.width - 8) / math.max(1, curve.length - 1);
    final path = Path();

    for (var i = 0; i < curve.length; i++) {
      final val = double.parse(curve[i].equity);
      final reportedDrawdown = double.parse(curve[i].drawdown);
      final peak = val + reportedDrawdown;
      final x = 4 + step * i;
      final yVal = y(val);

      if (i == 0) {
        path.moveTo(x, yVal);
      } else {
        path.lineTo(x, yVal);
      }

      if (reportedDrawdown > 0) {
        final drawPaint = Paint()
          ..color = drawdownColor
          ..strokeWidth = step + 1;
        canvas.drawLine(Offset(x, y(peak)), Offset(x, yVal), drawPaint);
      }
    }

    canvas.drawPath(
      path,
      Paint()
        ..color = line
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke,
    );

    if (selected >= 0 && selected < curve.length) {
      final x = 4 + step * selected;
      canvas.drawLine(
        Offset(x, top),
        Offset(x, size.height),
        Paint()
          ..color = cursor.withValues(alpha: 0.45)
          ..strokeWidth = 1,
      );
      canvas.drawCircle(
        Offset(x, y(double.parse(curve[selected].equity))),
        4,
        Paint()..color = line,
      );
    }
  }

  @override
  bool shouldRepaint(_EquityPainter oldDelegate) => true;
}
