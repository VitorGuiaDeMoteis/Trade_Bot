class ObserverStatus {
  final String status;
  final String? provider;
  final String? model;
  final String? modelVersion;
  final String? promptVersion;
  final DateTime? asOfUtc;
  final int? latencyMs;
  final String? errorCode;

  ObserverStatus({
    required this.status,
    this.provider,
    this.model,
    this.modelVersion,
    this.promptVersion,
    this.asOfUtc,
    this.latencyMs,
    this.errorCode,
  });

  factory ObserverStatus.fromJson(Map<String, dynamic> json) {
    return ObserverStatus(
      status: json['status'],
      provider: json['provider'],
      model: json['model'],
      modelVersion: json['model_version'],
      promptVersion: json['prompt_version'],
      asOfUtc: json['as_of_utc'] != null ? DateTime.parse(json['as_of_utc']) : null,
      latencyMs: json['latency_ms'],
      errorCode: json['error_code'],
    );
  }
}

class ObserverAnalysisItem {
  final String analysisId;
  final DateTime? asOfUtc;
  final DateTime createdAt;
  final String status;
  final String? regime;
  final double? confidence;
  final int riskFlagsCount;
  final String provider;
  final String model;
  final String modelVersion;
  final String promptVersion;
  final int latencyMs;
  final String? fallback;

  ObserverAnalysisItem({
    required this.analysisId,
    this.asOfUtc,
    required this.createdAt,
    required this.status,
    this.regime,
    this.confidence,
    required this.riskFlagsCount,
    required this.provider,
    required this.model,
    required this.modelVersion,
    required this.promptVersion,
    required this.latencyMs,
    this.fallback,
  });

  factory ObserverAnalysisItem.fromJson(Map<String, dynamic> json) {
    return ObserverAnalysisItem(
      analysisId: json['analysis_id'],
      asOfUtc: json['as_of_utc'] != null ? DateTime.parse(json['as_of_utc']) : null,
      createdAt: DateTime.parse(json['created_at']),
      status: json['status'],
      regime: json['regime'],
      confidence: json['confidence']?.toDouble(),
      riskFlagsCount: json['risk_flags_count'] ?? 0,
      provider: json['provider'],
      model: json['model'],
      modelVersion: json['model_version'],
      promptVersion: json['prompt_version'],
      latencyMs: json['latency_ms'] ?? 0,
      fallback: json['fallback'],
    );
  }
}

class RiskFlag {
  final String code;
  final String severity;
  final String message;

  RiskFlag({required this.code, required this.severity, required this.message});

  factory RiskFlag.fromJson(Map<String, dynamic> json) {
    return RiskFlag(
      code: json['code'],
      severity: json['severity'],
      message: json['message'],
    );
  }
}

class ObserverAnalysisDetail {
  final String analysisId;
  final DateTime? asOfUtc;
  final DateTime createdAt;
  final String provider;
  final String model;
  final String modelVersion;
  final String promptVersion;
  final String schemaVersion;
  final String? inputHash;
  final String? outputHash;
  final int latencyMs;
  final String status;
  final String? errorCode;
  final String? fallback;
  
  final String? regimeLabel;
  final double? regimeConfidence;
  final List<String> regimeEvidence;
  final List<RiskFlag> riskFlags;
  final List<String> observations;

  ObserverAnalysisDetail({
    required this.analysisId,
    this.asOfUtc,
    required this.createdAt,
    required this.provider,
    required this.model,
    required this.modelVersion,
    required this.promptVersion,
    required this.schemaVersion,
    this.inputHash,
    this.outputHash,
    required this.latencyMs,
    required this.status,
    this.errorCode,
    this.fallback,
    this.regimeLabel,
    this.regimeConfidence,
    required this.regimeEvidence,
    required this.riskFlags,
    required this.observations,
  });

  factory ObserverAnalysisDetail.fromJson(Map<String, dynamic> json) {
    final vo = json['validated_output'];
    
    String? rLabel;
    double? rConf;
    List<String> rEvid = [];
    List<RiskFlag> rFlags = [];
    List<String> obs = [];
    
    if (vo != null) {
      if (vo['regime'] != null) {
        rLabel = vo['regime']['label'];
        rConf = vo['regime']['confidence']?.toDouble();
        if (vo['regime']['evidence'] != null) {
          rEvid = List<String>.from(vo['regime']['evidence']);
        }
      }
      if (vo['risk_flags'] != null) {
        rFlags = (vo['risk_flags'] as List).map((i) => RiskFlag.fromJson(i)).toList();
      }
      if (vo['observations'] != null) {
        obs = List<String>.from(vo['observations']);
      }
    }

    return ObserverAnalysisDetail(
      analysisId: json['analysis_id'],
      asOfUtc: json['as_of_utc'] != null ? DateTime.parse(json['as_of_utc']) : null,
      createdAt: DateTime.parse(json['created_at']),
      provider: json['provider'],
      model: json['model'],
      modelVersion: json['model_version'],
      promptVersion: json['prompt_version'],
      schemaVersion: json['schema_version'],
      inputHash: json['input_hash'],
      outputHash: json['output_hash'],
      latencyMs: json['latency_ms'] ?? 0,
      status: json['status'],
      errorCode: json['error_code'],
      fallback: json['fallback'],
      regimeLabel: rLabel,
      regimeConfidence: rConf,
      regimeEvidence: rEvid,
      riskFlags: rFlags,
      observations: obs,
    );
  }
}
