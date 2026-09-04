import 'package:flutter/foundation.dart';
import 'api.dart';
import 'models.dart';

enum ObserverState { loading, loaded, error }

class ObserverController extends ChangeNotifier {
  final HttpObserverApi api;

  ObserverState state = ObserverState.loading;
  ObserverStatus? currentStatus;
  List<ObserverAnalysisItem> timeline = [];
  String? errorMessage;

  ObserverController({required this.api});

  Future<void> load() async {
    state = ObserverState.loading;
    errorMessage = null;
    notifyListeners();

    try {
      final statusFuture = api.getStatus();
      final timelineFuture = api.getAnalyses();

      final results = await Future.wait([statusFuture, timelineFuture]);
      currentStatus = results[0] as ObserverStatus;
      timeline = results[1] as List<ObserverAnalysisItem>;
      
      state = ObserverState.loaded;
    } catch (e) {
      state = ObserverState.error;
      errorMessage = e.toString();
    }
    notifyListeners();
  }
}

class ObserverDetailController extends ChangeNotifier {
  final HttpObserverApi api;
  final String analysisId;

  ObserverState state = ObserverState.loading;
  ObserverAnalysisDetail? detail;
  String? errorMessage;

  ObserverDetailController({required this.api, required this.analysisId});

  Future<void> load() async {
    state = ObserverState.loading;
    errorMessage = null;
    notifyListeners();

    try {
      detail = await api.getAnalysisDetail(analysisId);
      state = ObserverState.loaded;
    } catch (e) {
      state = ObserverState.error;
      errorMessage = e.toString();
    }
    notifyListeners();
  }
}
