import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

class HttpObserverApi {
  final String baseUrl;
  final http.Client client;

  HttpObserverApi(this.baseUrl, [http.Client? client]) : client = client ?? http.Client();

  Future<ObserverStatus> getStatus() async {
    final response = await client.get(Uri.parse('$baseUrl/api/v1/observer/status'));
    if (response.statusCode == 200) {
      return ObserverStatus.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to load observer status');
  }

  Future<List<ObserverAnalysisItem>> getAnalyses() async {
    final response = await client.get(Uri.parse('$baseUrl/api/v1/observer/analyses'));
    if (response.statusCode == 200) {
      final List list = jsonDecode(response.body);
      return list.map((item) => ObserverAnalysisItem.fromJson(item)).toList();
    }
    throw Exception('Failed to load observer analyses');
  }

  Future<ObserverAnalysisDetail> getAnalysisDetail(String analysisId) async {
    final response = await client.get(Uri.parse('$baseUrl/api/v1/observer/analyses/$analysisId'));
    if (response.statusCode == 200) {
      return ObserverAnalysisDetail.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to load analysis detail');
  }
}
