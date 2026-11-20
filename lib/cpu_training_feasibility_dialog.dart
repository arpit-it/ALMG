import 'dart:convert';
import 'package:flutter/material.dart';

class CpuTrainingFeasibilityDialog extends StatelessWidget {
  const CpuTrainingFeasibilityDialog({super.key, required this.report});
  final Map<String, dynamic> report;
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('CPU classifier feasibility'), scrollable: true,
    content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('This classifier trains on CPU without Metal or CUDA. Optional Qwen repair planning is separate from classifier fitting.'),
      Text(report['feasible'] == true ? 'Current resources cover estimated classifier reserves.' : 'This classifier cannot start with current resources.'),
      Text('Estimated memory reserve: ${report['estimates']['required_available_memory_bytes']} bytes · additional disk reserve: ${report['estimates']['required_free_disk_bytes']} bytes.'),
      const Text('Calculated sparse-feature and coefficient budgets, not measured peak memory. No duration prediction is available. Resources are checked again before fitting.'),
      for (final reason in report['blockers'] as List) Text(reason as String),
      ExpansionTile(title: const Text('View CPU classifier feasibility record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(report))]),
    ])), actions: [
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      if (report['feasible'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve CPU classifier training')),
    ]);
}
