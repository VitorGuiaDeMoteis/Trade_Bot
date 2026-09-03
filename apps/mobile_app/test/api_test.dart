import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile_app/src/market/api.dart';
import 'package:mobile_app/src/market/models.dart';
import 'support/market_fake.dart';

void main() {
  test('REST usa endereço configurado e transmite cursor/limite', () async {
    final api = HttpMarketApi(
      'http://example.test:8000',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/market/candles');
        expect(request.url.host, 'example.test');
        expect(request.url.queryParameters, {
          'after': '3',
          'through': '5',
          'stream_id': 'stream-1',
          'limit': '20',
        });
        return http.Response(jsonEncode(snapshotJson([4, 5])), 200);
      }),
    );
    final page = await api.history(
      after: 3,
      through: 5,
      streamId: 'stream-1',
      limit: 20,
    );
    expect(page.candles.first.close, '101.0000');
    api.dispose();
  });
  for (final code in [409, 503, 500]) {
    test('HTTP $code é classificado para recuperação', () async {
      final api = HttpMarketApi(
        'http://example.test',
        client: MockClient((_) async => http.Response('{}', code)),
      );
      await expectLater(
        api.history(),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.kind,
            'kind',
            code == 409
                ? FailureKind.reset
                : code == 503
                ? FailureKind.degraded
                : FailureKind.invalid,
          ),
        ),
      );
      api.dispose();
    });
  }
  for (final url in [
    '',
    'file:///tmp',
    'http://user:password@example.test',
    'http://example.test/extra',
  ]) {
    test('configuração inválida rejeitada: $url', () async {
      final api = HttpMarketApi(url);
      await expectLater(
        api.history(),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.kind,
            'kind',
            FailureKind.configuration,
          ),
        ),
      );
      api.dispose();
    });
  }
  test('invariantes e contrato inválidos rejeitados', () {
    for (final change in [
      {'volume': -1},
      {'high': '99.0000'},
      {'low': '102.0000'},
      {'open': 'NaN'},
      {'close_time': '2026-01-01T02:00:00Z'},
      {'timeframe': '5m'},
    ]) {
      expect(
        () => Candle.fromJson({...candleJson(1), ...change}),
        throwsFormatException,
      );
    }
    expect(
      () => Snapshot.fromJson({
        ...snapshotJson([1]),
        'schema_version': '2.0',
      }),
      throwsFormatException,
    );
  });
}
