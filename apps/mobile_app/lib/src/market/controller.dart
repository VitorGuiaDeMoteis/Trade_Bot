import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'models.dart';

class MarketController extends ChangeNotifier {
  MarketController({
    required this.api,
    this.retryDelays = const [
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 4),
      Duration(seconds: 8),
      Duration(seconds: 15),
    ],
    this.heartbeatTimeout = const Duration(seconds: 8),
  });

  final MarketApi api;
  final List<Duration> retryDelays;
  final Duration heartbeatTimeout;
  String _selectedSymbol = 'TEST';
  String get selectedSymbol => _selectedSymbol;

  List<Candle> get filteredCandles =>
      [...candles]..sort((a, b) => a.openTime.compareTo(b.openTime));

  void setSymbol(String symbol) {
    if (_selectedSymbol == symbol ||
        !(marketData?.symbols ?? []).contains(symbol)) {
      return;
    }
    ++_generation;
    _selectedSymbol = symbol;
    _retry?.cancel();
    _heartbeat?.cancel();
    unawaited(_subscription?.cancel());
    unawaited(_close(_socket));
    _socket = null;
    streamId = null;
    candles = const [];
    cursor = 0;
    lastUpdatedAt = null;
    _failures = 0;
    unawaited(_connect());
  }

  List<Candle> candles = const [];
  MarketConnectionState state = MarketConnectionState.loading;
  String? message, streamId;
  int cursor = 0;
  DateTime? lastUpdatedAt;
  MarketDataInfo? marketData;
  // Contadores para validar transporte real sem expor controles de teste na UI.
  int liveEvents = 0;
  int recoveredCandles = 0;
  int successfulConnections = 0;

  MarketSocket? _socket;
  StreamSubscription<Json>? _subscription;
  Timer? _retry, _heartbeat;
  int _generation = 0, _failures = 0;
  bool _disposed = false;

  Future<void> start() => _connect();

  bool _active(int generation) => !_disposed && generation == _generation;

  Future<void> _connect() async {
    if (_disposed) return;
    final generation = ++_generation;
    state = candles.isEmpty
        ? MarketConnectionState.loading
        : MarketConnectionState.connecting;
    message = null;
    notifyListeners();
    try {
      var fresh = streamId == null;
      Snapshot page;
      try {
        page = await api.history(
          symbol: _selectedSymbol == 'TEST' ? null : _selectedSymbol,
          after: fresh ? null : cursor,
          streamId: streamId,
        );
      } on ApiFailure catch (error) {
        if (error.kind != FailureKind.reset) rethrow;
        if (!_active(generation)) return;
        fresh = true;
        page = await api.history(
          symbol: _selectedSymbol == 'TEST' ? null : _selectedSymbol,
        );
      }
      if (!_active(generation)) return;
      _applyPage(page, fresh: fresh);
      while (page.hasMore) {
        page = await api.history(
          symbol: _selectedSymbol == 'TEST' ? null : _selectedSymbol,
          after: cursor,
          through: page.highWatermark,
          streamId: streamId,
        );
        if (!_active(generation)) return;
        _applyPage(page, fresh: false);
      }
      state = MarketConnectionState.connecting;
      notifyListeners();
      final socket = await api.connect(
        streamId!,
        cursor,
        symbol: _selectedSymbol,
      );
      if (!_active(generation)) {
        await _close(socket);
        return;
      }
      _socket = socket;
      successfulConnections++;
      _subscription = socket.messages.listen(
        (event) {
          if (!_active(generation)) return;
          try {
            _onMessage(event);
            _armHeartbeat(generation);
          } catch (error) {
            _failed(error, generation);
          }
        },
        onDone: () =>
            _failed(const ApiFailure(FailureKind.offline), generation),
        onError: (Object error) => _failed(error, generation),
        cancelOnError: true,
      );
      _armHeartbeat(generation);
    } catch (error) {
      _failed(error, generation);
    }
  }

  void _applyPage(Snapshot page, {required bool fresh}) {
    if (page.timeframe != '1h' ||
        (_selectedSymbol != 'TEST' && page.symbol != _selectedSymbol)) {
      throw const FormatException('Série diferente');
    }
    final previous = fresh ? 0 : cursor;
    if (!fresh && page.streamId != streamId) {
      throw const FormatException('Stream diferente');
    }
    var expected = fresh && page.candles.isNotEmpty
        ? page.candles.first.sequence
        : previous + 1;
    final ids = fresh ? <String>{} : candles.map((c) => c.id).toSet();
    final timesPerSymbol = <String, Set<DateTime>>{};
    if (!fresh) {
      for (final c in candles) {
        timesPerSymbol
            .putIfAbsent(c.symbol, () => <DateTime>{})
            .add(c.openTime);
      }
    }
    for (final candle in page.candles) {
      if (candle.streamId != page.streamId ||
          candle.symbol != page.symbol ||
          candle.timeframe != page.timeframe ||
          candle.provider != page.marketData.provider) {
        throw const FormatException(
          'Histórico inconsistente (stream diferente)',
        );
      }
      if (candle.sequence != expected++) {
        throw const FormatException(
          'Histórico inconsistente (sequência inválida)',
        );
      }
      if (!ids.add(candle.id)) {
        throw const FormatException('Histórico inconsistente (id duplicado)');
      }
      final times = timesPerSymbol.putIfAbsent(
        candle.symbol,
        () => <DateTime>{},
      );
      if (!times.add(candle.openTime)) {
        throw const FormatException(
          'Histórico inconsistente (tempo duplicado)',
        );
      }
    }
    if (page.candles.isEmpty && page.cursor != previous) {
      throw const FormatException('Cursor sem histórico');
    }
    if (!fresh) recoveredCandles += page.candles.length;
    final combined = [...(fresh ? <Candle>[] : candles), ...page.candles];
    candles = List.unmodifiable(
      combined.length > 2000
          ? combined.sublist(combined.length - 2000)
          : combined,
    );
    streamId = page.streamId;
    cursor = page.cursor;
    marketData = page.marketData;
    lastUpdatedAt = page.updatedAt ?? lastUpdatedAt;

    _selectedSymbol = page.symbol;
    notifyListeners();
  }

  void _onMessage(Json event) {
    if (event['schema_version'] != '2.0' || event['stream_id'] != streamId) {
      throw const FormatException('Contrato do stream inválido');
    }
    if (event['type'] == 'stream.status') {
      marketData = MarketDataInfo.fromJson(
        Map<String, dynamic>.from(event['market_data'] as Map),
      );
      state = event['database'] == 'up'
          ? marketData!.connectionState
          : MarketConnectionState.degraded;
      if (state == MarketConnectionState.degraded ||
          state == MarketConnectionState.configurationError) {
        message = 'Problema de conexão: ${state.name}';
      } else if (state == MarketConnectionState.offline ||
          state == MarketConnectionState.marketClosed) {
        message = state == MarketConnectionState.marketClosed
            ? 'Sessão regular fechada.'
            : 'Fonte offline.';
      } else {
        message = null;
      }
      _failures = 0;

      notifyListeners();
      return;
    }
    if (event['type'] != 'event' ||
        event['event_type'] != 'market.candle.closed') {
      throw const FormatException('Evento desconhecido');
    }
    final candle = Candle.fromJson(
      Map<String, dynamic>.from(event['payload'] as Map),
    );
    if (candle.streamId != streamId ||
        candle.sequence != event['sequence'] ||
        candle.symbol != _selectedSymbol ||
        candle.provider != marketData?.provider) {
      throw const FormatException('Identidade do candle inválida');
    }
    if (candle.sequence <= cursor) return;
    if (candle.sequence != cursor + 1) {
      throw const ApiFailure(FailureKind.degraded);
    }
    final isDuplicate = candles.any(
      (old) =>
          old.id == candle.id ||
          (old.symbol == candle.symbol && old.openTime == candle.openTime),
    );
    if (isDuplicate) {
      throw const ApiFailure(FailureKind.degraded);
    }
    candles = List.unmodifiable([
      ...candles.skip(candles.length >= 2000 ? 1 : 0),
      candle,
    ]);
    cursor = candle.sequence;
    liveEvents++;
    lastUpdatedAt = DateTime.parse(event['occurred_at'] as String);
    notifyListeners();
  }

  void _armHeartbeat(int generation) {
    _heartbeat?.cancel();
    _heartbeat = Timer(
      heartbeatTimeout,
      () => _failed(const ApiFailure(FailureKind.offline), generation),
    );
  }

  void _failed(Object error, int generation) {
    if (!_active(generation)) return;
    ++_generation;
    _heartbeat?.cancel();
    unawaited(_subscription?.cancel());
    unawaited(_close(_socket));
    _socket = null;
    final kind = error is ApiFailure
        ? error.kind
        : error is FormatException || error is TypeError
        ? FailureKind.invalid
        : FailureKind.offline;
    state = switch (kind) {
      FailureKind.degraded => MarketConnectionState.degraded,
      FailureKind.invalid ||
      FailureKind.configuration => MarketConnectionState.configurationError,
      _ => MarketConnectionState.offline,
    };
    message = switch (kind) {
      FailureKind.configuration =>
        'Endereço do servidor não configurado ou inválido.',
      FailureKind.invalid =>
        'Não foi possível ler os dados. Tentaremos novamente.',
      FailureKind.degraded =>
        'Dados temporariamente indisponíveis. Recuperando histórico.',
      _ =>
        'Conexão interrompida. O histórico permanece visível e a reconexão é automática.',
    };
    if (kind != FailureKind.configuration) {
      final delay = retryDelays[_failures.clamp(0, retryDelays.length - 1)];
      _failures++;
      _retry?.cancel();
      _retry = Timer(delay, () => unawaited(_connect()));
    }
    notifyListeners();
  }

  Future<void> retryNow() async {
    ++_generation;
    _retry?.cancel();
    _heartbeat?.cancel();
    unawaited(_subscription?.cancel());
    unawaited(_close(_socket));
    _socket = null;
    await _connect();
  }

  Future<void> _close(MarketSocket? socket) async {
    try {
      await socket?.close();
    } catch (_) {
      // Falha ao encerrar socket já perdido não altera a causa da desconexão.
    }
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    _retry?.cancel();
    _heartbeat?.cancel();
    unawaited(_subscription?.cancel());
    unawaited(_close(_socket));
    api.dispose();
    super.dispose();
  }
}
