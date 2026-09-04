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

    await tester.pumpWidget(MaterialApp(home: ObserverPage(controller: controller)));
    
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

    await tester.pumpWidget(MaterialApp(home: ObserverPage(controller: controller)));
    await tester.pumpAndSettle();
    
    expect(find.textContaining('Erro:'), findsOneWidget);
    expect(find.text('Tentar Novamente'), findsOneWidget);
  });

  testWidgets('disabled state', (tester) async {
    final api = MockObserverApi();
    api.status = ObserverStatus(status: 'DISABLED');
    
    final controller = ObserverController(api: api);

    await tester.pumpWidget(MaterialApp(home: ObserverPage(controller: controller)));
    await tester.pumpAndSettle();
    
    expect(find.textContaining('AI OBSERVER DESLIGADO'), findsOneWidget);
    expect(find.textContaining('Strategy: continua ativa'), findsOneWidget);
    expect(find.textContaining('Risk Engine: continua ativo'), findsOneWidget);
  });

  testWidgets('OK and timeline interaction', (tester) async {
    final api = MockObserverApi();
    api.status = ObserverStatus(
      status: 'OK', provider: 'simulator', model: 'test', latencyMs: 150
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
      )
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

    await tester.pumpWidget(MaterialApp(home: ObserverPage(controller: controller)));
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
      )
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

    await tester.pumpWidget(MaterialApp(home: ObserverPage(controller: controller)));
    await tester.pumpAndSettle();
    
    await tester.tap(find.byType(ListTile).first);
    await tester.pumpAndSettle();

    expect(find.text('AI OBSERVER DEGRADED'), findsOneWidget);
    expect(find.textContaining('Fallback interno: HOLD'), findsOneWidget);
    expect(find.textContaining('Esse HOLD pertence somente ao Observer e NÃO altera Strategy, Risk ou execução.'), findsOneWidget);
  });
}
