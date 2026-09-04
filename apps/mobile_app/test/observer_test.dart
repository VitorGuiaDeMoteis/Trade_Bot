import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/observer/api.dart';
import 'package:mobile_app/src/observer/controller.dart';
import 'package:mobile_app/src/observer/models.dart';
import 'package:mobile_app/src/observer/page.dart';

class MockObserverApi extends HttpObserverApi {
  MockObserverApi() : super('http://localhost');

  bool failNext = false;
  ObserverStatus status = ObserverStatus(status: 'DISABLED');
  List<ObserverAnalysisItem> analyses = [];
  ObserverAnalysisDetail? detail;

  @override
  Future<ObserverStatus> getStatus() async {
    if (failNext) throw Exception('API Error');
    return status;
  }

  @override
  Future<List<ObserverAnalysisItem>> getAnalyses() async {
    if (failNext) throw Exception('API Error');
    return analyses;
  }

  @override
  Future<ObserverAnalysisDetail> getAnalysisDetail(String analysisId) async {
    if (failNext) throw Exception('API Error');
    if (detail != null && detail!.analysisId == analysisId) {
      return detail!;
    }
    throw Exception('Not found');
  }
}

void main() {
  testWidgets('loading and empty states', (tester) async {
    final api = MockObserverApi();
    final controller = ObserverController(api: api);

    await tester.pumpWidget(
      MaterialApp(home: ObserverPage(controller: controller)),
    );

    // initially loading
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();

    // empty timeline
    expect(find.text('Nenhuma análise registrada'), findsOneWidget);
    expect(find.text('OBSERVADOR\nSEM AUTORIDADE DE EXECUÇÃO'), findsOneWidget);
  });

  testWidgets('error state', (tester) async {
    final api = MockObserverApi()..failNext = true;
    final controller = ObserverController(api: api);

    await tester.pumpWidget(
      MaterialApp(home: ObserverPage(controller: controller)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Erro:'), findsOneWidget);
    expect(find.text('Tentar Novamente'), findsOneWidget);
  });

  testWidgets('disabled state', (tester) async {
    final api = MockObserverApi();
    api.status = ObserverStatus(status: 'DEGRADED', errorCode: 'DISABLED');

    final controller = ObserverController(api: api);

    await tester.pumpWidget(
      MaterialApp(home: ObserverPage(controller: controller)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('AI OBSERVER DESLIGADO'), findsOneWidget);
    expect(
      find.textContaining('Strategy e Risk: não alterados pelo Observer'),
      findsOneWidget,
    );
    expect(find.textContaining('Paper: controle independente'), findsOneWidget);
  });

  testWidgets('OK and timeline interaction', (tester) async {
    final api = MockObserverApi();
    api.status = ObserverStatus(
      status: 'OK',
      provider: 'simulator',
      model: 'test',
      latencyMs: 150,
    );
    api.analyses = [
      ObserverAnalysisItem(
        analysisId: '123',
        createdAt: DateTime.now(),
        status: 'OK',
        regime: 'TRENDING',
        riskFlagsCount: 1,
        provider: 'simulator',
        model: 'test',
        modelVersion: '1',
        promptVersion: '1',
        latencyMs: 100,
      ),
    ];

    api.detail = ObserverAnalysisDetail(
      analysisId: '123',
      createdAt: DateTime.now(),
      provider: 'simulator',
      model: 'test',
      modelVersion: '1',
      promptVersion: '1',
      schemaVersion: '1',
      latencyMs: 100,
      status: 'OK',
      regimeLabel: 'TRENDING',
      regimeConfidence: 0.8,
      regimeEvidence: ['Evidência 1'],
      riskFlags: [RiskFlag(code: 'VOL', severity: 'HIGH', message: 'Cuidado')],
      observations: ['Obs 1'],
    );

    final controller = ObserverController(api: api);

    await tester.pumpWidget(
      MaterialApp(home: ObserverPage(controller: controller)),
    );
    await tester.pumpAndSettle();

    // Tap on the timeline item
    await tester.tap(find.byType(ListTile).first);
    await tester.pumpAndSettle();

    // Check detail page
    expect(find.text('TRENDING'), findsOneWidget);
    expect(find.text('Confiança reportada pelo modelo: 80.0%'), findsOneWidget);
    expect(find.textContaining('Evidência 1'), findsOneWidget);
    expect(find.text('VOL (HIGH)'), findsOneWidget);
    expect(find.textContaining('Obs 1'), findsOneWidget);
  });

  testWidgets('DEGRADED and fallback HOLD internal', (tester) async {
    final api = MockObserverApi();
    api.status = ObserverStatus(status: 'DEGRADED');
    api.analyses = [
      ObserverAnalysisItem(
        analysisId: '456',
        createdAt: DateTime.now(),
        status: 'DEGRADED',
        riskFlagsCount: 0,
        provider: 'simulator',
        model: 'test',
        modelVersion: '1',
        promptVersion: '1',
        latencyMs: 100,
      ),
    ];

    api.detail = ObserverAnalysisDetail(
      analysisId: '456',
      createdAt: DateTime.now(),
      provider: 'simulator',
      model: 'test',
      modelVersion: '1',
      promptVersion: '1',
      schemaVersion: '1',
      latencyMs: 100,
      status: 'DEGRADED',
      fallback: 'HOLD',
      regimeEvidence: [],
      riskFlags: [],
      observations: [],
    );

    final controller = ObserverController(api: api);

    await tester.pumpWidget(
      MaterialApp(home: ObserverPage(controller: controller)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byType(ListTile).first);
    await tester.pumpAndSettle();

    expect(find.text('AI OBSERVER DEGRADED'), findsOneWidget);
    expect(find.textContaining('Fallback interno: HOLD'), findsOneWidget);
    expect(
      find.textContaining(
        'Esse HOLD pertence somente ao Observer e NÃO altera Strategy, Risk ou execução.',
      ),
      findsOneWidget,
    );
  });
  testWidgets('landscape 2x keeps status and timeline scrollable', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(960, 600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = MockObserverApi();
    api.status = ObserverStatus(
      status: 'DEGRADED',
      provider: 'docker',
      model: 'local-observer',
      modelVersion: 'sha256:${'a' * 64}',
      promptVersion: 'observer-v1',
      errorCode: 'TIMEOUT',
      latencyMs: 50,
    );
    final controller = ObserverController(api: api);
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(2)),
          child: child!,
        ),
        home: ObserverPage(controller: controller),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.scrollUntilVisible(
      find.text('Nenhuma análise registrada'),
      200,
    );
    expect(tester.takeException(), isNull);
  });
  for (final size in [const Size(600, 960), const Size(960, 600)]) {
    testWidgets('detail audit and disabled separation at 2x $size', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(size);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = MockObserverApi();
      api.detail = ObserverAnalysisDetail(
        analysisId: '3800434b-af16-4c8a-9763-caa489bf29dd',
        createdAt: DateTime.utc(2026, 9, 4),
        provider: 'docker',
        model: 'local-observer',
        modelVersion: 'sha256:${'a' * 64}',
        promptVersion: 'observer-v1',
        schemaVersion: '1.0',
        latencyMs: 0,
        status: 'DEGRADED',
        fallback: 'HOLD',
        errorCode: 'DISABLED',
        regimeEvidence: [],
        riskFlags: [],
        observations: [],
      );
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(2)),
            child: child!,
          ),
          home: ObserverDetailPage(
            controller: ObserverDetailController(
              api: api,
              analysisId: api.detail!.analysisId,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('AI OBSERVER DESLIGADO'), findsOneWidget);
      expect(
        find.textContaining('Observer HOLD ≠ Strategy HOLD.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(find.text('AUDITORIA'), 250);
      await tester.scrollUntilVisible(find.text('DISABLED'), 250);
      expect(tester.takeException(), isNull);
    });
  }
}
