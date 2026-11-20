import 'dart:convert';
import 'package:flutter/material.dart';

class GeneratedTrialFeasibilityDialog extends StatelessWidget {
  const GeneratedTrialFeasibilityDialog({super.key, required this.report});
  final Map<String, dynamic> report;
  @override Widget build(BuildContext context) => AlertDialog(
    title: Text(report['factory'] != null ? 'Factory decoder trial feasibility' : report['resume'] != null ? 'Resume decoder trial feasibility' : report['dataset'] != null ? 'Reviewed dataset decoder feasibility' : 'Generated decoder trial feasibility'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (report['factory'] != null) const Text('This hardware review is tied to the selected from-scratch approach. Confirmation creates a linked saved trial; no model release is approved.'),
      if (report['resume'] != null) Text('Resume binds to the saved approval and checkpoint file hashes: ${report['resume']['checkpoint']['completed_steps']} completed steps. Files are rechecked before submission. With no saved checkpoint, this bounded trial restarts from fresh weights.'),
      if (report['resume'] == null && report['dataset'] != null) Text('This reviewed local dataset uses ${report['dataset']['vocabulary_size']} tokens and ${report['dataset']['window_counts']['train']} training windows. Train a fresh width-8 decoder for 100 Metal SGD steps with a step-50 checkpoint. No model release is approved.'),
      if (report['resume'] == null && report['dataset'] == null) const Text('This fixed generated-text fixture trains a tiny fresh decoder on Metal and checks a step-50 checkpoint against uninterrupted training. It uses no downloaded student weights. Training and release need separate approval.'),
      Text(report['feasible'] == true ? 'Current resources cover the calculated fixed-trial reserves.' : 'This saved trial cannot start with current hardware/resources.'),
      Text('Device: ${report['hardware']['metal_device']?['device_name'] ?? 'Metal unavailable'} · MLX ${report['hardware']['mlx_version'] ?? 'unavailable'}'),
      Text('Calculated memory reserve: ${report['estimates']['required_available_memory_bytes']} bytes · disk reserve: ${report['estimates']['required_free_disk_bytes']} bytes.'),
      const Text('These are calculated reserves, not measured peaks or a duration prediction. This report covers only the reviewed scope and data. Resources are checked again before and during fitting.'),
      if (report['estimates']['worker_work_estimate'] != null) Text('Estimated saved-trial worker work: ${report['estimates']['worker_work_estimate']['estimated_seconds']} s from ${report['estimates']['worker_work_estimate']['sample_count']} compatible completed measurement(s), highest observed time plus 25%. Includes training, evaluation and checkpoint/bundle saving. Excludes queue, approval and idle/AC waits. A heuristic, not an upper bound; total wall time remains unknown.'),
      for (final reason in report['blockers'] as List) Text(reason as String),
      ExpansionTile(title: Text(report['factory'] != null ? 'View factory hardware record' : report['resume'] != null ? 'View resume hardware record' : report['dataset'] != null ? 'View reviewed dataset hardware record' : 'View generated trial hardware record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(report))]),
    ])), actions: [
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      if (report['feasible'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: Text(report['factory'] != null ? 'Approve factory decoder trial' : report['resume'] != null ? 'Approve saved trial resume' : report['dataset'] != null ? 'Approve reviewed dataset decoder trial' : 'Approve generated decoder trial')),
    ]);
}
