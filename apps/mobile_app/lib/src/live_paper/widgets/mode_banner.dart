import 'package:flutter/material.dart';

import '../format.dart';
import '../models.dart';

/// Permanent mode banner — never color-only.
class ModeBanner extends StatelessWidget {
  const ModeBanner({
    super.key,
    required this.mode,
    required this.simulatedMoney,
    required this.marketStatus,
    this.brokerConnected = false,
    this.updatedAt,
    this.stale = false,
    this.mockPreview = false,
  });

  final LivePaperMode mode;
  final bool simulatedMoney;
  final MarketStatus marketStatus;
  final bool brokerConnected;
  final DateTime? updatedAt;
  final bool stale;
  final bool mockPreview;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final marketLabel = marketStatusLabel(marketStatus);
    final marketIcon = switch (marketStatus) {
      MarketStatus.open => Icons.circle,
      MarketStatus.closed => Icons.nightlight_round,
      MarketStatus.degraded => Icons.warning_amber_rounded,
      MarketStatus.unknown => Icons.help_outline,
    };
    final marketColor = switch (marketStatus) {
      MarketStatus.open => const Color(0xFF3DDC97),
      MarketStatus.closed => colors.onSurfaceVariant,
      MarketStatus.degraded => const Color(0xFFE6A23C),
      MarketStatus.unknown => colors.onSurfaceVariant,
    };

    return Container(
      key: const Key('mode-banner'),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: 0.55),
        border: Border(
          bottom: BorderSide(color: colors.outlineVariant.withValues(alpha: 0.5)),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (mockPreview)
            const Padding(
              padding: EdgeInsets.only(bottom: 6),
              child: Text(
                'MOCK / DESIGN PREVIEW',
                key: Key('mock-watermark'),
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.1,
                  fontSize: 11,
                  color: Color(0xFFE6A23C),
                ),
              ),
            ),
          Text(
            modeTitle(mode),
            key: const Key('mode-label'),
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (simulatedMoney)
                const _TextChip(
                  key: Key('fake-money-badge'),
                  label: 'DINHEIRO FICTÍCIO',
                  icon: Icons.science_outlined,
                ),
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 6,
                children: [
                  Icon(marketIcon, size: 12, color: marketColor),
                  Text(
                    marketLabel,
                    key: const Key('market-status'),
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: marketColor,
                      letterSpacing: 0.8,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 16,
            runSpacing: 4,
            children: [
              Text(
                brokerConnected ? 'conectado' : 'broker offline',
                key: const Key('broker-status'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              Text(
                'atualização ${clockLabel(updatedAt)}',
                key: const Key('last-update'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (stale)
                Text(
                  'DADOS ATRASADOS',
                  key: const Key('stale-market'),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFFE6A23C),
                    fontWeight: FontWeight.w700,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TextChip extends StatelessWidget {
  const _TextChip({super.key, required this.label, required this.icon});
  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        border: Border.all(
          color: Theme.of(context).colorScheme.outlineVariant,
        ),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 6,
        children: [
          Icon(icon, size: 14),
          Text(
            label,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}
