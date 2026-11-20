import 'dart:convert';
import 'package:flutter/material.dart';

class StreamTrialEvaluationDialog extends StatefulWidget {
  const StreamTrialEvaluationDialog({super.key, required this.run, required this.request});
  final Map<String, dynamic> run;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<StreamTrialEvaluationDialog> createState() => _StreamTrialEvaluationDialogState();
}

class _StreamTrialEvaluationDialogState extends State<StreamTrialEvaluationDialog> {
  Map<String, dynamic>? _report;
  bool _busy = false;
  String? _error;
  Future<void> _evaluate() async {
    setState(() { _busy = true; _error = null; _report = null; });
    try {
      final report = await widget.request('/decoder-stream-training-runs/${widget.run['id']}/evaluate', {
        'confirmed': true, 'reviewed_revision': widget.run['revision'],
      });
      if (mounted) setState(() { _report = report; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  Future<void> _history() async {
    setState(() { _busy = true; _error = null; });
    try {
      final reports = (await widget.request('/decoder-stream-training-runs/${widget.run['id']}/evaluations', {
        'confirmed': true, 'reviewed_revision': widget.run['revision'],
      }))['reports'] as List;
      if (!mounted) return;
      setState(() => _busy = false);
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved independent CPU evaluations'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved independent evaluations.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['passed'] == true ? 'target met' : 'target not met'}')),
        ]));
      if (selected != null && mounted) setState(() => _report = selected);
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Independent saved-model evaluation'), scrollable: true,
    content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Reload the saved model and tokenizer and evaluate every saved validation/test window on this machine using CPU. '
        'Padding is excluded and results are weighted by real target tokens. Large splits can take time. '
        'Evaluate saves a private report; interruption requires rerunning the check. No training, external request, export approval or model release runs.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_report != null) ...[
        Text(_report!['passed'] == true ? '80% accuracy target met on both splits. No release approved.' : '80% accuracy target not met. No release approved.'),
        for (final split in ['validation', 'test']) Text('$split: ${_report!['evaluation'][split]['windows']} windows · '
          '${_report!['evaluation'][split]['target_tokens']} targets · accuracy ${_report!['evaluation'][split]['next_token_accuracy']} · loss ${_report!['evaluation'][split]['loss']}'),
        ExpansionTile(title: const Text('View independent evaluation record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_report))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved CPU evaluations')),
      TextButton(onPressed: _busy ? null : _evaluate, child: const Text('Evaluate saved model on CPU')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
