import 'dart:convert';
import 'package:flutter/material.dart';

class DecoderCorpusContinuationDialog extends StatefulWidget {
  const DecoderCorpusContinuationDialog({super.key, required this.sourceId, required this.request});
  final String sourceId;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderCorpusContinuationDialog> createState() => _DecoderCorpusContinuationDialogState();
}
class _DecoderCorpusContinuationDialogState extends State<DecoderCorpusContinuationDialog> {
  Map<String, dynamic>? _review;
  bool _busy = false;
  String? _error;
  String get _path => '/decoder-corpus-optimizer-runs/${widget.sourceId}';
  Future<void> _perform(Future<void> Function() action) async {
    setState(() { _busy = true; _error = null; });
    try { await action(); } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _load() => _perform(() async {
    setState(() => _review = null);
    final review = await widget.request('$_path/continuation-review', {});
    if (mounted) setState(() => _review = review);
  });
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved corpus checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 650, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Restored update ${record['restored_step']} · finished update ${record['completed_steps']} · reference weight difference ${record['reference_parameter_max_error']}.'),
      Text('Generated text: ${record['generated_text']}'),
      const Text('Separate private result; the original corpus run is preserved. No model release or broader language-quality acceptance is established.'),
      SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
    ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _continue() => _perform(() async {
    final record = await widget.request('$_path/continue', {'confirmed': true, 'reviewed': _review});
    if (mounted) await _show(record);
  });
  Future<void> _history() => _perform(() async {
    final result = await widget.request('$_path/continuations', {});
    if (!mounted) return;
    setState(() => _busy = false);
    final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Saved corpus checkpoint continuations'), children: [
        if ((result['records'] as List).isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No corpus continuations saved for this run.')),
        for (final record in result['records'] as List) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
          child: Text('${(record['id'] as String).substring(0, 8)} · restored ${record['restored_step']} → ${record['completed_steps']}')),
      ]));
    if (selected != null && mounted) await _show(selected);
  });
  @override Widget build(BuildContext context) => AlertDialog(title: const Text('Review corpus checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Restore the saved midpoint model, FP32 optimizer moments and scheduler counter. Complete only the remaining original updates using the original corpus windows and precision settings, then compare with the saved final model. Save a new private model, tokenizer and optimizer state. Original artifacts stay unchanged. This path does not expose cancellation or arbitrary interrupted-run recovery yet.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text('Restore update ${_review!['restore_step']} · remaining updates ${_review!['estimates']['optimizer_updates']}.'),
        Text(_review!['feasible'] == true ? 'Resources cover corpus continuation reserves.' : 'Corpus continuation cannot start.'),
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View corpus continuation review'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved corpus checkpoint continuations')),
      TextButton(onPressed: _busy ? null : _load, child: const Text('Review corpus continuation resources')),
      if (_review?['feasible'] == true) TextButton(onPressed: _busy ? null : _continue, child: const Text('Confirm continue corpus checkpoint')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
