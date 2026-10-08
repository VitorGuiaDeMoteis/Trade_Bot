import 'models.dart';

String formatMoney(String? raw, {String currency = 'USD', bool signed = false}) {
  if (raw == null) return '—';
  final value = double.tryParse(raw);
  if (value == null) return raw;
  final abs = value.abs().toStringAsFixed(2);
  final parts = abs.split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+(?!\d))'),
    (m) => '${m[1]},',
  );
  final formatted = '\$$whole.${parts[1]}';
  if (!signed) {
    return value < 0 ? '-$formatted' : formatted;
  }
  if (value > 0) return '+$formatted';
  if (value < 0) return '-$formatted';
  return formatted;
}

String formatPct(String? raw, {bool signed = true}) {
  if (raw == null) return '—';
  final value = double.tryParse(raw);
  if (value == null) return '$raw%';
  final body = '${value.abs().toStringAsFixed(2)}%';
  if (!signed) return body;
  if (value > 0) return '+$body';
  if (value < 0) return '-$body';
  return body;
}

double? parseDecimal(String? raw) {
  if (raw == null) return null;
  return double.tryParse(raw);
}

String clockLabel(DateTime? utc) {
  if (utc == null) return '—';
  final local = utc.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(local.hour)}:${two(local.minute)}:${two(local.second)}';
}

String relativeLabel(DateTime? utc, {DateTime? now}) {
  if (utc == null) return '—';
  final reference = (now ?? DateTime.now()).toUtc();
  final delta = reference.difference(utc.toUtc());
  if (delta.inSeconds < 60) return 'há ${delta.inSeconds}s';
  if (delta.inMinutes < 60) return 'há ${delta.inMinutes} min';
  if (delta.inHours < 48) return 'há ${delta.inHours} h';
  return 'há ${delta.inDays} d';
}

String modeTitle(LivePaperMode mode) => switch (mode) {
  LivePaperMode.alpacaPaper => 'ALPACA PAPER',
  LivePaperMode.localPaper => 'LOCAL PAPER',
  LivePaperMode.backtest => 'BACKTEST',
  LivePaperMode.aiObserver => 'AI OBSERVER',
  LivePaperMode.unknown => 'MODO DESCONHECIDO',
};

String marketStatusLabel(MarketStatus status) => switch (status) {
  MarketStatus.open => 'OPEN',
  MarketStatus.closed => 'CLOSED',
  MarketStatus.degraded => 'DEGRADED',
  MarketStatus.unknown => 'UNKNOWN',
};

String riskStatusLabel(RiskLevel level) => switch (level) {
  RiskLevel.normal => 'NORMAL',
  RiskLevel.paused => 'PAUSED',
  RiskLevel.degraded => 'DEGRADED',
};
