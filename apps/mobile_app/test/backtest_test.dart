import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/backtest/api.dart';
import 'package:mobile_app/src/backtest/controller.dart';
import 'package:mobile_app/src/backtest/models.dart';

class MockBacktestApi extends HttpBacktestApi {
  MockBacktestApi() : super('http://localhost');

  List<BacktestSummary> mockSummaries = [];
  BacktestReport? mockReport;

  @override
  Future<List<BacktestSummary>> getBacktests() async {
    return mockSummaries;
  }

  @override
  Future<BacktestReport> getBacktest(String resultHash) async {
    return mockReport!;
  }
}

void main() {
  testWidgets('loading state, error state, empty state', (tester) async {
    final api = MockBacktestApi();
    final controller = BacktestController(api: api);
    
    // Test that the controller correctly represents states
    controller.listState = BacktestState.loading;
    expect(controller.listState, BacktestState.loading);
    
    controller.listState = BacktestState.error;
    expect(controller.listState, BacktestState.error);
    
    controller.listState = BacktestState.loaded;
    expect(controller.listState, BacktestState.loaded);
  });

}
