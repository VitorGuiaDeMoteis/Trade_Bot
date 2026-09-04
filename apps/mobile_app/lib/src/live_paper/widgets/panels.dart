import 'package:flutter/material.dart';

import '../format.dart';
import '../models.dart';

class AccountPanel extends StatelessWidget {
  const AccountPanel({super.key, required this.account});

  final LiveAccountInfo account;

  @override
  Widget build(BuildContext context) {
    final day = parseDecimal(account.dayPnl);
    final total = parseDecimal(account.totalPnl);
    final dayColor = _pnlColor(day);
    final totalColor = _pnlColor(total);

    return _Panel(
      key: const Key('account-panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('EQUITY', style: _labelStyle(context)),
          Text(
            formatMoney(account.equity, currency: account.currency),
            key: const Key('equity-value'),
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${formatMoney(account.dayPnl, signed: true)} dia',
            key: const Key('day-pnl'),
            style: TextStyle(
              color: dayColor,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 16),
          Text('CASH', style: _labelStyle(context)),
          Text(
            formatMoney(account.cash, currency: account.currency),
            key: const Key('cash-value'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 20,
            runSpacing: 8,
            children: [
              _MiniMetric(
                label: 'BUYING POWER',
                value: formatMoney(account.buyingPower),
                keyName: 'buying-power',
              ),
              _MiniMetric(
                label: 'TOTAL P&L',
                value: formatMoney(account.totalPnl, signed: true),
                keyName: 'total-pnl',
                color: totalColor,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Color? _pnlColor(double? value) {
    if (value == null) return null;
    if (value > 0) return const Color(0xFF3DDC97);
    if (value < 0) return const Color(0xFFFF6B6B);
    return null;
  }

  TextStyle? _labelStyle(BuildContext context) =>
      Theme.of(context).textTheme.labelMedium?.copyWith(
        letterSpacing: 0.8,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      );
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({
    required this.label,
    required this.value,
    required this.keyName,
    this.color,
  });

  final String label;
  final String value;
  final String keyName;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        Text(
          value,
          key: Key(keyName),
          style: TextStyle(fontWeight: FontWeight.w600, color: color),
        ),
      ],
    );
  }
}

class RiskPanel extends StatelessWidget {
  const RiskPanel({super.key, required this.risk});

  final LiveRiskInfo risk;

  @override
  Widget build(BuildContext context) {
    final level = risk.level;
    final label = riskStatusLabel(level);
    final accent = switch (level) {
      RiskLevel.normal => const Color(0xFF3DDC97),
      RiskLevel.paused => const Color(0xFFE6A23C),
      RiskLevel.degraded => const Color(0xFFFF6B6B),
    };
    final explicit = switch (level) {
      RiskLevel.paused => 'NOVAS ORDENS BLOQUEADAS',
      RiskLevel.degraded => 'EXECUÇÃO BLOQUEADA',
      RiskLevel.normal => null,
    };

    return _Panel(
      key: const Key('risk-panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'RISK',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              letterSpacing: 0.8,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Icon(
                switch (level) {
                  RiskLevel.normal => Icons.verified_user_outlined,
                  RiskLevel.paused => Icons.pause_circle_outline,
                  RiskLevel.degraded => Icons.block,
                },
                color: accent,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                label,
                key: const Key('risk-status'),
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: accent,
                  letterSpacing: 0.6,
                ),
              ),
            ],
          ),
          if (explicit != null) ...[
            const SizedBox(height: 8),
            Text(
              explicit,
              key: const Key('risk-explicit'),
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: accent,
              ),
            ),
          ],
          if (risk.reason != null && risk.reason!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(risk.reason!, style: Theme.of(context).textTheme.bodySmall),
          ],
        ],
      ),
    );
  }
}

class DecisionPanel extends StatelessWidget {
  const DecisionPanel({super.key, this.decision});

  final LiveLatestDecision? decision;

  @override
  Widget build(BuildContext context) {
    if (decision == null) {
      return const _Panel(
        key: Key('decision-panel'),
        child: Text('Nenhuma decisão registrada'),
      );
    }
    final d = decision!;
    return _Panel(
      key: const Key('decision-panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'ÚLTIMA DECISÃO',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              letterSpacing: 0.8,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Registro do sistema — não é recomendação',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 12),
          _ChainStep(label: 'SIGNAL', value: '${d.symbol}  ${d.signal}', keyName: 'decision-signal'),
          const _ChainArrow(),
          _ChainStep(label: 'RISK', value: d.risk, keyName: 'decision-risk'),
          const _ChainArrow(),
          _ChainStep(
            label: 'RESULTADO',
            value: d.risk.toUpperCase() == 'APPROVED'
                ? 'aprovado para execução'
                : d.risk.toUpperCase() == 'REJECTED'
                ? 'bloqueado'
                : d.risk,
            keyName: 'decision-result',
          ),
          const SizedBox(height: 10),
          Text(
            '${d.timeframe} · Strategy ${d.strategyVersion ?? d.reason ?? '—'} · ${relativeLabel(d.createdAt)}',
            key: const Key('decision-meta'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _ChainStep extends StatelessWidget {
  const _ChainStep({
    required this.label,
    required this.value,
    required this.keyName,
  });
  final String label;
  final String value;
  final String keyName;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        Text(
          value,
          key: Key(keyName),
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _ChainArrow extends StatelessWidget {
  const _ChainArrow();
  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 4),
    child: Icon(Icons.arrow_downward, size: 16),
  );
}

class PositionsPanel extends StatelessWidget {
  const PositionsPanel({super.key, required this.positions});

  final List<LivePosition> positions;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      key: const Key('positions-panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'POSIÇÕES',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              letterSpacing: 0.8,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          if (positions.isEmpty)
            const Text(
              'Nenhuma posição aberta',
              key: Key('positions-empty'),
            )
          else
            ...positions.map((p) {
              final pnl = parseDecimal(p.unrealizedPnl);
              final color = pnl == null
                  ? null
                  : pnl > 0
                  ? const Color(0xFF3DDC97)
                  : pnl < 0
                  ? const Color(0xFFFF6B6B)
                  : null;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Wrap(
                  spacing: 12,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      p.symbol,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    Text('qty ${p.qty}'),
                    Text(formatMoney(p.marketValue)),
                    Text(
                      '${formatMoney(p.unrealizedPnl, signed: true)} (${formatPct(p.unrealizedPnlPct)})',
                      style: TextStyle(color: color, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

class OrdersPanel extends StatelessWidget {
  const OrdersPanel({super.key, required this.orders, this.compact = false});

  final List<LiveOrder> orders;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final visible = compact ? orders.take(5).toList() : orders;
    return _Panel(
      key: const Key('orders-panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            compact ? 'ORDENS RECENTES' : 'ORDENS',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              letterSpacing: 0.8,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          if (visible.isEmpty)
            const Text('Nenhuma ordem recente', key: Key('orders-empty'))
          else
            ...visible.map((o) => _OrderRow(order: o)),
        ],
      ),
    );
  }
}

class _OrderRow extends StatelessWidget {
  const _OrderRow({required this.order});
  final LiveOrder order;

  @override
  Widget build(BuildContext context) {
    final statusColor = switch (order.status) {
      OrderStatus.filled => const Color(0xFF3DDC97),
      OrderStatus.partial || OrderStatus.pending => const Color(0xFFE6A23C),
      OrderStatus.rejected => const Color(0xFFFF6B6B),
      OrderStatus.canceled || OrderStatus.unknown =>
        Theme.of(context).colorScheme.onSurfaceVariant,
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Wrap(
        spacing: 10,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(clockLabel(order.submittedAt)),
          Text(
            '${order.side} ${order.symbol}',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          Text('qty ${order.qty}'),
          if (order.filledQty != null) Text('filled ${order.filledQty}'),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              border: Border.all(color: statusColor.withValues(alpha: 0.6)),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              order.statusLabel,
              key: Key('order-status-${order.statusLabel}'),
              style: TextStyle(
                color: statusColor,
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
          if (order.fillPrice != null) Text('@ ${formatMoney(order.fillPrice)}'),
        ],
      ),
    );
  }
}

class ObserverSummaryCard extends StatelessWidget {
  const ObserverSummaryCard({
    super.key,
    this.summary,
    this.onOpen,
  });

  final ObserverSummary? summary;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final s = summary;
    final degraded = s?.isDegraded == true;
    final status = s?.status ?? '—';
    return _Panel(
      key: const Key('observer-summary'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                'AI OBSERVER',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  letterSpacing: 0.8,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              if (onOpen != null)
                TextButton(
                  onPressed: onOpen,
                  child: const Text('Abrir'),
                ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'OBSERVADOR · SEM AUTORIDADE DE EXECUÇÃO',
            key: Key('observer-no-authority'),
            style: TextStyle(
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Status: $status',
            key: const Key('observer-status'),
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: degraded
                  ? const Color(0xFFE6A23C)
                  : status == 'OK'
                  ? const Color(0xFF3DDC97)
                  : null,
            ),
          ),
          if (degraded)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text(
                'DEGRADED',
                key: Key('observer-degraded-label'),
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: Color(0xFFE6A23C),
                ),
              ),
            ),
          if (s?.regime != null)
            Text('${s!.regime} · confidence ${((s.confidence ?? 0) * 100).toStringAsFixed(0)}%'),
          if (s?.lastAnalysisAt != null)
            Text('Última análise ${relativeLabel(s!.lastAnalysisAt)}'),
        ],
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
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
      child: child,
    );
  }
}
