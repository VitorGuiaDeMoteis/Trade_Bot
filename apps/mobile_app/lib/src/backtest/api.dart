import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';
class HttpBacktestApi {
  HttpBacktestApi(this.baseUrl);
  final String baseUrl;

  Future<List<BacktestSummary>> getBacktests() async {
    final response = await http.get(Uri.parse('$baseUrl/api/v1/backtests'));
    if (response.statusCode != 200) {
      throw Exception('Falha ao listar backtests: ${response.statusCode}');
    }
    final List<dynamic> jsonList = jsonDecode(response.body);
    return jsonList.map((j) => BacktestSummary.fromJson(j)).toList();
  }

  Future<BacktestReport> getBacktest(String resultHash) async {
    final response = await http.get(Uri.parse('$baseUrl/api/v1/backtests/$resultHash'));
    if (response.statusCode != 200) {
      throw Exception('Falha ao carregar backtest: ${response.statusCode}');
    }
    return BacktestReport.fromJson(jsonDecode(response.body));
  }
  
  String getExportUrl(String resultHash) {
    return '$baseUrl/api/v1/backtests/$resultHash/export';
  }
}
