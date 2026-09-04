import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile_app/src/paper/controller.dart';
import 'package:mobile_app/src/paper/page.dart';

Map<String, dynamic> portfolio(bool paused) => {
  'run_id': 'paper-run',
  'status': 'RUNNING',
  'provider': 'simulator',
  'paused': paused,
  'step': 2,
  'initial_cash': '10000',
  'cash': '9099.459955',
  'market_value': '900',
  'equity': '9999.459955',
  'total_pnl': '-0.540045',
  'unrealized_pnl': '-0.45',
  'realized_pnl': '0',
  'fees': '0.090045',
  'positions': [
    {
      'symbol': 'TEST',
      'quantity': 9,
      'market_value': '900',
      'unrealized_pnl': '-0.45',
    },
  ],
  'orders': [],
  'fills': [],
};

void main() {
  test(
    'native STOP contract: empty POST, no secret, refresh and no repeated pause',
    () async {
      var paused = false;
      var posts = 0;
      final controller = PaperController(
        apiUrl: 'http://127.0.0.1:8000',
        client: MockClient((r) async {
          if (r.method == 'POST') {
            expect(r.url.path, '/api/v1/paper/pause');
            expect(r.body, isEmpty);
            expect(
              r.headers['X-Paper-Control'] ?? r.headers['x-paper-control'],
              'stop',
            );
            expect(
              r.headers.keys.map((k) => k.toLowerCase()),
              isNot(contains('authorization')),
            );
            posts++;
            paused = true;
            return http.Response('{"paused":true}', 200);
          }
          return http.Response(jsonEncode(portfolio(paused)), 200);
        }),
      );
      await controller.loadPortfolio();
      final before = controller.portfolio!;
      await controller.pause();
      await controller.pause();
      expect(posts, 1);
      expect(controller.isPaused, isTrue);
      expect(controller.portfolio!.cash, before.cash);
      expect(controller.portfolio!.positions.single.quantity, 9);
      controller.dispose();
    },
  );

  for (final failure in ['denied', 'unconfirmed', 'offline']) {
    test('failed STOP stays unconfirmed: $failure', () async {
      final controller = PaperController(
        apiUrl: 'http://127.0.0.1:8000',
        client: MockClient((r) async {
          if (r.method == 'GET') {
            return http.Response(jsonEncode(portfolio(false)), 200);
          }
          if (failure == 'offline') throw const SocketException('offline');
          return http.Response(
            '{"paused":false}',
            failure == 'denied' ? 403 : 200,
          );
        }),
      );
      await controller.loadPortfolio();
      await controller.pause();
      expect(controller.isPaused, isFalse);
      expect(controller.error, contains('Pausa não confirmada'));
      expect(controller.portfolio!.cash, 9099.459955);
      controller.dispose();
    });
  }

  test(
    'confirmed STOP survives failed refresh and keeps last portfolio visible',
    () async {
      var stopped = false;
      final controller = PaperController(
        apiUrl: 'http://127.0.0.1:8000',
        client: MockClient((r) async {
          if (r.method == 'POST') {
            stopped = true;
            return http.Response('{"paused":true}', 200);
          }
          if (stopped) throw const SocketException('offline');
          return http.Response(jsonEncode(portfolio(false)), 200);
        }),
      );
      await controller.loadPortfolio();
      await controller.pause();
      expect(controller.isPaused, isTrue);
      expect(controller.error, contains('Pausa confirmada'));
      expect(controller.portfolio!.positions.single.quantity, 9);
      controller.dispose();
    },
  );

  test('dispose during request does not notify a dead page', () async {
    final response = Completer<http.Response>();
    final controller = PaperController(
      apiUrl: 'http://127.0.0.1:8000',
      client: MockClient((r) => response.future),
    );
    final pending = controller.loadPortfolio();
    controller.dispose();
    response.complete(http.Response(jsonEncode(portfolio(false)), 200));
    await pending;
  });

  for (final size in [
    const Size(360, 800),
    const Size(800, 360),
    const Size(800, 1280),
    const Size(1280, 800),
  ]) {
    testWidgets('button pauses and portfolio remains visible at $size', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var stopped = false;
      final controller = PaperController(
        apiUrl: 'http://127.0.0.1:8000',
        client: MockClient((r) async {
          if (r.method == 'POST') {
            stopped = true;
            return http.Response('{"paused":true}', 200);
          }
          return http.Response(jsonEncode(portfolio(stopped)), 200);
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: PaperPage(controller: controller),
        ),
      );
      await tester.pumpAndSettle();
      final button = find.byKey(const Key('pause-paper'));
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      expect(tester.getSize(button).height, greaterThanOrEqualTo(48));
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(stopped, isTrue);
      expect(find.text('SIMULAÇÃO PAUSADA'), findsOneWidget);
      expect(
        find.textContaining('Para retomar, use a CLI local.'),
        findsOneWidget,
      );
      expect(find.text('PAUSAR SIMULAÇÃO'), findsNothing);
      expect(find.text('Cash: \$9099.46'), findsOneWidget);
      await tester.tap(find.text('Positions'));
      await tester.pumpAndSettle();
      expect(find.text('TEST'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    });
  }

  test('Flutter contains no old control credentials or resume toggle', () {
    final sources = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))
        .map((f) => f.readAsStringSync())
        .join('\n');
    expect(
      sources.contains(
        'local-'
        'admin',
      ),
      isFalse,
    );
    expect(
      sources.contains(
        'toggle'
        'Pause',
      ),
      isFalse,
    );
    expect(
      sources.contains(
        'RE'
        'SUME',
      ),
      isFalse,
    );
    expect(sources.contains('PAPER_CONTROL_TOKEN'), isFalse);
  });
}
