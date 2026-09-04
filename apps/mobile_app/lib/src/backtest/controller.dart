import 'package:flutter/foundation.dart';
import 'api.dart';
import 'models.dart';

enum BacktestState { loading, loaded, error }

class BacktestController extends ChangeNotifier {
  BacktestController({required this.api});
  
  final HttpBacktestApi api;
  
  BacktestState listState = BacktestState.loading;
  List<BacktestSummary> summaries = [];
  String? errorMessage;
  
  BacktestState detailState = BacktestState.loading;
  BacktestReport? currentReport;
  String? detailErrorMessage;

  int replayIndex = 0;

  Future<void> loadSummaries() async {
    listState = BacktestState.loading;
    errorMessage = null;
    notifyListeners();
    try {
      summaries = await api.getBacktests();
      listState = BacktestState.loaded;
    } catch (e) {
      listState = BacktestState.error;
      errorMessage = e.toString();
    }
    notifyListeners();
  }

  Future<void> loadReport(String resultHash) async {
    detailState = BacktestState.loading;
    detailErrorMessage = null;
    currentReport = null;
    replayIndex = 0;
    notifyListeners();
    try {
      currentReport = await api.getBacktest(resultHash);
      detailState = BacktestState.loaded;
    } catch (e) {
      detailState = BacktestState.error;
      detailErrorMessage = e.toString();
    }
    notifyListeners();
  }

  void clearReport() {
    currentReport = null;
    notifyListeners();
  }
  
  void setReplayIndex(int index) {
    if (currentReport != null && index >= 0 && index < currentReport!.equityCurve.length) {
      replayIndex = index;
      notifyListeners();
    }
  }
  
  void advanceReplay() {
    setReplayIndex(replayIndex + 1);
  }
  
  void rewindReplay() {
    setReplayIndex(replayIndex - 1);
  }
}
