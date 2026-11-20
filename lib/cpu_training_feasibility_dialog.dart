import 'dart:convert';
import 'package:flutter/material.dart';

class CpuTrainingFeasibilityDialog extends StatelessWidget {
  const CpuTrainingFeasibilityDialog({super.key, required this.report, this.title = 'CPU classifier feasibility',
    this.description = 'This classifier trains on CPU without Metal or CUDA. Optional Qwen repair planning is separate from classifier fitting.',
    this.approvalLabel = 'Approve CPU classifier training', this.recordLabel = 'View CPU classifier feasibility record'});
  final Map<String, dynamic> report;
  final String title, description, approvalLabel, recordLabel;
  @override Widget build(BuildContext context) => AlertDialog(
    title: Text(title), scrollable: true,
    content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(description),
      Text(report['feasible'] == true ? 'Current resources cover estimated recipe reserves.' : 'This recipe cannot start with current resources.'),
      Text('Estimated memory reserve: ${report['estimates']['required_available_memory_bytes']} bytes · additional disk reserve: ${report['estimates']['required_free_disk_bytes']} bytes.'),
      const Text('Calculated recipe-specific buffer/model budgets, not measured peak memory. No duration prediction is available. Resources are checked again before fitting.'),
      for (final reason in report['blockers'] as List) Text(reason as String),
      ExpansionTile(title: Text(recordLabel), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(report))]),
    ])), actions: [
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      if (report['feasible'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: Text(approvalLabel)),
    ]);
}
