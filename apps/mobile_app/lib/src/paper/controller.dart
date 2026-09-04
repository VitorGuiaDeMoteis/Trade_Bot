import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'models.dart';

class PaperController extends ChangeNotifier {
  PaperController({
    this.apiUrl = const String.fromEnvironment('API_BASE_URL'),
    http.Client? client,
    this.timeout = const Duration(seconds: 5),
  }) : _client = client ?? http.Client();

  final String apiUrl;
  final http.Client _client;
  final Duration timeout;
  PaperPortfolio? portfolio;
  bool isLoading = false;
  bool _pauseConfirmed = false;
  bool _disposed = false;
  String? error;
  bool get isPaused => _pauseConfirmed || (portfolio?.paused ?? false);

  Uri _url(String path) {
    final base = Uri.tryParse(apiUrl);
    if (base == null ||
        !['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment ||
        (base.path.isNotEmpty && base.path != '/')) {
      throw const FormatException(
        'Configure API_BASE_URL para o backend local.',
      );
    }
    return base.replace(path: '/api/v1/paper/$path');
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _fetchPortfolio() async {
    final res = await _client.get(_url('portfolio')).timeout(timeout);
    if (res.statusCode != 200) throw StateError('portfolio unavailable');
    final result = PaperPortfolio.fromJson(jsonDecode(res.body) as Json);
    if (_disposed) return;
    portfolio = result;
    _pauseConfirmed = result.paused;
  }

  Future<void> loadPortfolio() async {
    if (isLoading || _disposed) return;
    isLoading = true;
    error = null;
    _notify();
    try {
      await _fetchPortfolio();
    } catch (_) {
      error =
          'Não foi possível atualizar a carteira. Verifique o backend local.';
    } finally {
      isLoading = false;
      _notify();
    }
  }

  Future<void> pause() async {
    if (isLoading || isPaused || _disposed) return;
    isLoading = true;
    error = null;
    _notify();
    try {
      // Intent marker, NOT a secret. Server accepts only native loopback STOP.
      final res = await _client
          .post(_url('pause'), headers: {'X-Paper-Control': 'stop'})
          .timeout(timeout);
      if (res.statusCode != 200 ||
          (jsonDecode(res.body) as Json)['paused'] != true) {
        throw StateError('pause not confirmed');
      }
      _pauseConfirmed = true;
      try {
        await _fetchPortfolio();
      } catch (_) {
        error =
            'Pausa confirmada. Carteira ainda não atualizada; exibindo última consulta.';
      }
    } catch (_) {
      error = 'Pausa não confirmada. Atualize a carteira ou tente novamente.';
    } finally {
      isLoading = false;
      _notify();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _client.close();
    super.dispose();
  }
}
