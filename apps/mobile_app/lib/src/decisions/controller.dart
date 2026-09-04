import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../market/api.dart';
import 'api.dart';
import 'models.dart';

class DecisionsController extends ChangeNotifier {
  DecisionsController({required this.api});
  final DecisionsApi api;
  DecisionsSnapshot? snapshot;
  String? selectedSymbol;
  List<String> symbols = [];
  bool loading = true;
  String? message;
  int _generation = 0;
  bool _disposed = false;

  Future<void> select(String symbol) async {
    if (symbol == selectedSymbol) return;
    selectedSymbol = symbol;
    snapshot = null;
    await refresh();
  }

  Future<void> refresh() async {
    final generation = ++_generation;
    final requested = selectedSymbol;
    loading = true;
    message = null;
    notifyListeners();
    try {
      final result = await api.fetch(symbol: requested);
      if (_disposed || generation != _generation) return;
      if (requested != null && result.symbol != requested) {
        throw const FormatException('Ativo diferente do solicitado');
      }
      snapshot = result;
      selectedSymbol = result.symbol;
      symbols = result.symbols;
    } catch (error) {
      if (_disposed || generation != _generation) return;
      message = switch (error) {
        ApiFailure(kind: FailureKind.configuration) =>
          'Configure a URL do backend.',
        ApiFailure(kind: FailureKind.degraded) =>
          'Banco indisponível. Tente atualizar.',
        SocketException() ||
        http.ClientException() ||
        TimeoutException() => 'Offline. Não foi possível consultar o backend.',
        _ => 'Resposta inválida. Não foi possível carregar as decisões.',
      };
    }
    if (!_disposed && generation == _generation) {
      loading = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    api.dispose();
    super.dispose();
  }
}
