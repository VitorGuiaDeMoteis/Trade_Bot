import 'dart:convert';
import 'package:http/http.dart' as http;
import '../market/api.dart';
import '../market/models.dart';
import 'models.dart';

abstract class DecisionsApi {
  Future<DecisionsSnapshot> fetch({String? symbol});
  void dispose();
}

class HttpDecisionsApi implements DecisionsApi {
  HttpDecisionsApi(this.baseUrl, {http.Client? client})
    : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;

  @override
  Future<DecisionsSnapshot> fetch({String? symbol}) async {
    final base = Uri.tryParse(baseUrl);
    if (base == null ||
        !['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment ||
        (base.path.isNotEmpty && base.path != '/')) {
      throw const ApiFailure(FailureKind.configuration);
    }
    final response = await _client
        .get(
          base.replace(
            path: '/api/v1/decisions',
            queryParameters: {
              'symbol': ?symbol,
              'timeframe': '1h',
              'limit': '50',
            },
          ),
        )
        .timeout(const Duration(seconds: 5));
    if (response.statusCode == 503) {
      throw const ApiFailure(FailureKind.degraded);
    }
    if (response.statusCode != 200) {
      throw const ApiFailure(FailureKind.invalid);
    }
    return DecisionsSnapshot.fromJson(jsonDecode(response.body) as Json);
  }

  @override
  void dispose() => _client.close();
}
