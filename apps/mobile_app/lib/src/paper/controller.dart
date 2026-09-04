import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'models.dart';

class PaperController extends ChangeNotifier {
  PaperController({this.apiUrl = 'http://10.0.2.2:8000'});

  final String apiUrl;
  PaperPortfolio? portfolio;
  bool isLoading = false;
  String? error;

  Future<void> loadPortfolio() async {
    isLoading = true;
    error = null;
    notifyListeners();

    try {
      final res = await http.get(Uri.parse('$apiUrl/api/v1/paper/portfolio'));
      if (res.statusCode == 200) {
        portfolio = PaperPortfolio.fromJson(jsonDecode(res.body));
      } else {
        error = 'Failed to load paper portfolio: ${res.statusCode}';
      }
    } catch (e) {
      error = e.toString();
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> togglePause(bool pause) async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final res = await http.post(
        Uri.parse('$apiUrl/api/v1/paper/pause'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'paused': pause, 'token': 'local-admin'}),
      );
      if (res.statusCode == 200) {
        await loadPortfolio();
      } else {
        error = 'Failed to toggle pause: ${res.statusCode}';
      }
    } catch (e) {
      error = e.toString();
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }
}
