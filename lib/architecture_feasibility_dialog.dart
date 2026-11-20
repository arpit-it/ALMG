import 'dart:convert';
import 'package:flutter/material.dart';

class ArchitectureFeasibilityDialog extends StatefulWidget {
  const ArchitectureFeasibilityDialog({super.key, required this.initialized, required this.request});
  final Map<String, dynamic> initialized;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<ArchitectureFeasibilityDialog> createState() => _ArchitectureFeasibilityDialogState();
}

class _ArchitectureFeasibilityDialogState extends State<ArchitectureFeasibilityDialog> {
  String _precision = 'float32';
  Map<String, dynamic>? _report;
  String? _error;
  bool _busy = true;
  @override void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() { _busy = true; _report = null; _error = null; });
    try {
      final report = await widget.request('/decoder-architecture-plans/${widget.initialized['plan_id']}/feasibility', {
        'confirmed': true, 'reviewed': widget.initialized, 'precision': _precision, 'device': 'metal',
      });
      if (mounted) setState(() { _report = report; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  String _mib(dynamic bytes) => bytes is num ? '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MiB' : 'unavailable';
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Backward-check hardware feasibility'), scrollable: true,
    content: SizedBox(width: 660, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Review hardware and conservative reserves before five synthetic Metal SGD steps. Updated weights are discarded; only a private numerical report is saved. '
        'This assessment covers this bounded diagnostic, not full dataset training. CPU forward inspection is separate; this backward check has no CPU or CUDA fallback.'),
      DropdownButton<String>(value: _precision, items: [for (final precision in ['float32', 'float16', 'bfloat16']) DropdownMenuItem(value: precision, child: Text(precision))],
        onChanged: _busy ? null : (value) { if (value != null) { _precision = value; _load(); } }),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_report != null) ...[
        Text(_report!['feasible'] == true ? 'Current resources cover the conservative diagnostic reserves.' : 'This diagnostic cannot start with the selected configuration/resources.'),
        Text('Device: ${_report!['hardware']['metal_device']?['device_name'] ?? 'Metal unavailable'} · MLX ${_report!['hardware']['mlx_version'] ?? 'unavailable'}'),
        Text('Observed memory: ${_mib(_report!['hardware']['available_memory_bytes'])} available / ${_mib(_report!['hardware']['total_memory_bytes'])} total · disk ${_mib(_report!['hardware']['free_disk_bytes'])} free'),
        Text('Calculated reserves: ${_mib(_report!['estimates']['required_available_memory_bytes'])} memory · ${_mib(_report!['estimates']['required_free_disk_bytes'])} disk'),
        if ((_report!['calibration']?['compatible_reports'] as List?)?.isNotEmpty == true)
          Text('Calibrated with ${(_report!['calibration']['compatible_reports'] as List).length} compatible isolated diagnostic report(s). '
            'Observed Metal peak: ${_mib(_report!['calibration']['observed_metal_peak_bytes'])}; process peak RSS: ${_mib(_report!['calibration']['observed_process_peak_rss_bytes'])}. '
            'Measurements can only raise reserves. CPU and GPU memory may overlap; the admission sum is conservative. This applies only to the same synthetic diagnostic.'),
        if (_report!['estimates']['diagnostic_work_estimate'] != null)
          Text('Estimated complete synthetic diagnostic work: ${_report!['estimates']['diagnostic_work_estimate']['estimated_seconds']} s, based on ${_report!['estimates']['diagnostic_work_estimate']['sample_count']} compatible report(s), highest observed workflow time plus 25%. Includes model loading, feasibility and CPU numerical checks. Excludes interpreter/import startup, approval waits and report publication. A heuristic, not an upper bound or full-training prediction.'),
        const Text('Calculated estimates and compatible measured diagnostic peaks are distinct. No full-training peak or duration prediction is available. Existing model loading and execution reserves are included; runtime exhaustion is still possible. Resources are checked again at execution.'),
        for (final reason in _report!['blockers'] as List) Text(reason as String),
        if (_report!['recommendation'] != null) Text('Smaller suggestion: ${_report!['recommendation']['config']['layers']} layers · width ${_report!['recommendation']['config']['hidden_size']} · '
          '${_report!['recommendation']['config']['attention_heads']} heads. Not applied: save, initialize and review a new plan first.'),
        ExpansionTile(title: const Text('View hardware feasibility record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_report))]),
      ],
    ])), actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      if (!_busy && _report?['feasible'] == true) TextButton(onPressed: () => Navigator.pop(context, _report), child: const Text('Confirm planned-model backward check')),
    ]);
}
