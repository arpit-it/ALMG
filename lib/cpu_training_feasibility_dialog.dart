import 'dart:convert';
import 'package:flutter/material.dart';

class CpuTrainingFeasibilityDialog extends StatelessWidget {
  const CpuTrainingFeasibilityDialog({super.key, required this.report, this.title = 'CPU classifier feasibility',
    this.description = 'This classifier trains on CPU without Metal or CUDA. Optional Qwen repair planning is separate from classifier fitting.',
    this.approvalLabel = 'Approve CPU classifier training', this.recordLabel = 'View CPU classifier feasibility record', this.measure, this.history});
  final Map<String, dynamic> report;
  final String title, description, approvalLabel, recordLabel;
  final Future<Map<String, dynamic>> Function(Map<String, dynamic>)? measure;
  final Future<Map<String, dynamic>> Function()? history;
  Future<void> _show(BuildContext context, String title, Map<String, dynamic> data) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: Text(title), scrollable: true, content: SizedBox(width: 660, child: SelectableText(const JsonEncoder.withIndent('  ').convert(data))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _measure(BuildContext context) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Run a discarded CPU resource trial?'),
      content: const Text('Fit this prepared classifier dataset once now, without Qwen repair or idle scheduling. Discard temporary models and save only timing/memory evidence. Main training and release remain unapproved.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm discarded CPU trial'))]));
    if (confirmed != true || !context.mounted) return;
    showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const PopScope(canPop: false,
      child: AlertDialog(title: Text('Measuring CPU classifier resources'), content: LinearProgressIndicator())));
    try {
      final result = await measure!(report);
      if (!context.mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); await _show(context, 'Discarded CPU resource trial', result);
    } catch (error) {
      if (!context.mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); await _show(context, 'CPU resource trial error', {'error': error.toString()});
    }
  }
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
      if (history != null) TextButton(onPressed: () async {
        try { final result = await history!(); if (context.mounted) await _show(context, 'Saved CPU resource trials', result); }
        catch (error) { if (context.mounted) await _show(context, 'CPU trial history error', {'error': error.toString()}); }
      }, child: const Text('View saved CPU resource trials')),
      if (measure != null && report['feasible'] == true && report['settings']?['allow_repair'] != true)
        TextButton(onPressed: () => _measure(context), child: const Text('Measure discarded CPU fit')),
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      if (report['feasible'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: Text(approvalLabel)),
    ]);
}
