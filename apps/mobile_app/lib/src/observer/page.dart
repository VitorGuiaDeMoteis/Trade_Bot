import 'package:flutter/material.dart';
import 'controller.dart';
import 'models.dart';

String _formatDate(DateTime dt) {
  return '${dt.year.toString().padLeft(4, '0')}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class ObserverPage extends StatefulWidget {
  final ObserverController controller;

  const ObserverPage({super.key, required this.controller});

  @override
  State<ObserverPage> createState() => _ObserverPageState();
}

class _ObserverPageState extends State<ObserverPage> {
  @override
  void initState() {
    super.initState();
    widget.controller.load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Observer'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: widget.controller.load,
          ),
        ],
      ),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: widget.controller,
          builder: (context, _) {
            if (widget.controller.state == ObserverState.loading) {
              return const Center(child: CircularProgressIndicator());
            }
            if (widget.controller.state == ObserverState.error) {
              return Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(
                      Icons.error_outline,
                      size: 48,
                      color: Colors.red,
                    ),
                    const SizedBox(height: 16),
                    Text('Erro: ${widget.controller.errorMessage}'),
                    const SizedBox(height: 16),
                    ElevatedButton(
                      onPressed: widget.controller.load,
                      child: const Text('Tentar Novamente'),
                    ),
                  ],
                ),
              );
            }

            final status = widget.controller.currentStatus;
            final timeline = widget.controller.timeline;

            return CustomScrollView(
              slivers: [
                SliverToBoxAdapter(child: _buildHeaderWarning()),
                if (status != null)
                  SliverToBoxAdapter(child: _buildStatusCard(status)),
                const SliverToBoxAdapter(child: Divider()),
                if (timeline.isEmpty)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('Nenhuma análise registrada'),
                    ),
                  )
                else
                  SliverList.builder(
                    itemCount: timeline.length,
                    itemBuilder: (context, index) =>
                        _buildTimelineItem(context, timeline[index]),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeaderWarning() {
    return Container(
      width: double.infinity,
      color: Colors.deepPurple[900],
      padding: const EdgeInsets.all(8.0),
      child: const Text(
        'OBSERVADOR\nSEM AUTORIDADE DE EXECUÇÃO',
        textAlign: TextAlign.center,
        style: TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  Widget _buildStatusCard(ObserverStatus status) {
    final displayStatus = status.errorCode == 'DISABLED'
        ? 'DISABLED'
        : status.status;
    Color statusColor;
    if (displayStatus == 'OK') {
      statusColor = Colors.green;
    } else if (displayStatus == 'DISABLED') {
      statusColor = Colors.grey;
    } else {
      statusColor = Colors.orange;
    }

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.psychology, color: statusColor, size: 32),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Status: $displayStatus',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: statusColor,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (displayStatus == 'DISABLED')
                const Text(
                  'AI OBSERVER DESLIGADO\n\nStrategy e Risk: não alterados pelo Observer\nPaper: controle independente',
                  style: TextStyle(color: Colors.orangeAccent),
                ),
              if (displayStatus != 'DISABLED') ...[
                Text('Provider: ${status.provider ?? 'N/A'}'),
                Text(
                  'Model: ${status.model ?? 'N/A'} (${status.modelVersion ?? 'N/A'})',
                ),
                Text('Prompt Version: ${status.promptVersion ?? 'N/A'}'),
                if (status.asOfUtc != null)
                  Text(
                    'Data base do snapshot: ${_formatDate(status.asOfUtc!.toLocal())}',
                  ),
                Text('Latência: ${status.latencyMs ?? 0} ms'),
                if (status.errorCode != null)
                  Text(
                    'Último erro: ${status.errorCode}',
                    style: const TextStyle(color: Colors.redAccent),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTimelineItem(BuildContext context, ObserverAnalysisItem item) {
    final displayStatus = item.errorCode == 'DISABLED'
        ? 'DISABLED'
        : item.status;
    Color itemColor = Colors.grey;
    if (item.status == 'OK') itemColor = Colors.green;
    if (item.status == 'DEGRADED') itemColor = Colors.orange;

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: itemColor.withValues(alpha: 0.2),
        child: Icon(Icons.analytics, color: itemColor),
      ),
      title: Text(_formatDate(item.createdAt.toLocal())),
      subtitle: Text(
        'Status: $displayStatus | ${item.errorCode ?? 'Sem erro'} | Regime: ${item.regime ?? 'N/A'} | Riscos: ${item.riskFlagsCount}',
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ObserverDetailPage(
              controller: ObserverDetailController(
                api: widget.controller.api,
                analysisId: item.analysisId,
              ),
            ),
          ),
        );
      },
    );
  }
}

class ObserverDetailPage extends StatefulWidget {
  final ObserverDetailController controller;

  const ObserverDetailPage({super.key, required this.controller});

  @override
  State<ObserverDetailPage> createState() => _ObserverDetailPageState();
}

class _ObserverDetailPageState extends State<ObserverDetailPage> {
  @override
  void initState() {
    super.initState();
    widget.controller.load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detalhe da Análise')),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: widget.controller,
          builder: (context, _) {
            if (widget.controller.state == ObserverState.loading) {
              return const Center(child: CircularProgressIndicator());
            }
            if (widget.controller.state == ObserverState.error) {
              return Center(
                child: Text('Erro: ${widget.controller.errorMessage}'),
              );
            }

            final detail = widget.controller.detail;
            if (detail == null) return const SizedBox.shrink();

            return SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'OBSERVADOR\nSEM AUTORIDADE DE EXECUÇÃO',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.deepPurpleAccent,
                    ),
                  ),
                  const SizedBox(height: 16),
                  _buildHeader(detail),
                  const SizedBox(height: 16),
                  if (detail.status == 'DEGRADED' || detail.fallback == 'HOLD')
                    _buildDegradedNotice(detail),
                  const SizedBox(height: 16),
                  _buildRegime(detail),
                  const SizedBox(height: 16),
                  _buildEvidences(detail),
                  const SizedBox(height: 16),
                  _buildRiskFlags(detail),
                  const SizedBox(height: 16),
                  _buildObservations(detail),
                  const SizedBox(height: 16),
                  _buildAudit(detail),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeader(ObserverAnalysisDetail detail) {
    return Text(
      detail.asOfUtc != null
          ? 'Data base: ${_formatDate(detail.asOfUtc!.toLocal())}'
          : 'Data base desconhecida',
      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
    );
  }

  Widget _buildDegradedNotice(ObserverAnalysisDetail detail) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      color: Colors.orange[900],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            detail.errorCode == 'DISABLED'
                ? 'AI OBSERVER DESLIGADO'
                : 'AI OBSERVER DEGRADED',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 16,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Observer HOLD ≠ Strategy HOLD.\n\nFallback interno: HOLD\n\nEsse HOLD pertence somente ao Observer e NÃO altera Strategy, Risk ou execução.',
            style: TextStyle(color: Colors.white),
          ),
        ],
      ),
    );
  }

  Widget _buildRegime(ObserverAnalysisDetail detail) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'REGIME',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.blueAccent,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              detail.regimeLabel ?? 'N/A',
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            if (detail.regimeConfidence != null)
              Text(
                'Confiança reportada pelo modelo: ${(detail.regimeConfidence! * 100).toStringAsFixed(1)}%',
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildEvidences(ObserverAnalysisDetail detail) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'EVIDÊNCIAS',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.blueAccent,
              ),
            ),
            const SizedBox(height: 8),
            if (detail.regimeEvidence.isEmpty)
              const Text('Nenhuma evidência fornecida pelo provider.'),
            ...detail.regimeEvidence.map(
              (e) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4.0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• ', style: TextStyle(fontSize: 18)),
                    Expanded(child: Text(e)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRiskFlags(ObserverAnalysisDetail detail) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'RISK FLAGS',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.redAccent,
              ),
            ),
            const SizedBox(height: 8),
            if (detail.riskFlags.isEmpty)
              const Text('Nenhuma flag de risco identificada.'),
            ...detail.riskFlags.map(
              (f) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 8.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${f.code} (${f.severity})',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    Text(f.message),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildObservations(ObserverAnalysisDetail detail) {
    if (detail.observations.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'OBSERVATIONS',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.blueAccent,
              ),
            ),
            const SizedBox(height: 8),
            ...detail.observations.map(
              (o) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4.0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• ', style: TextStyle(fontSize: 18)),
                    Expanded(child: Text(o)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAudit(ObserverAnalysisDetail detail) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'AUDITORIA',
              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey),
            ),
            const SizedBox(height: 8),
            _auditRow('Analysis ID', detail.analysisId),
            _auditRow(
              'Criada em UTC',
              detail.createdAt.toUtc().toIso8601String(),
            ),
            _auditRow('Model Provider', detail.provider),
            _auditRow('Model', detail.model),
            _auditRow('Model Version', detail.modelVersion),
            _auditRow('Prompt Version', detail.promptVersion),
            _auditRow('Schema Version', detail.schemaVersion),
            _auditRow('Input Hash', _shorten(detail.inputHash)),
            _auditRow('Output Hash', _shorten(detail.outputHash)),
            _auditRow('Latency', '${detail.latencyMs} ms'),
            _auditRow('Status', detail.status),
            if (detail.errorCode != null)
              _auditRow('Error Code', detail.errorCode!),
          ],
        ),
      ),
    );
  }

  String _shorten(String? hash) {
    if (hash == null) return 'N/A';
    if (hash.length <= 16) return hash;
    return '${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}';
  }

  Widget _auditRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
