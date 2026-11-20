import 'dart:convert';
import 'package:flutter/material.dart';

class DecoderOptimizerContinuationDialog extends StatefulWidget {
  const DecoderOptimizerContinuationDialog({super.key, required this.sourceId, required this.request});
  final String sourceId;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderOptimizerContinuationDialog> createState() => _DecoderOptimizerContinuationDialogState();
}

class _DecoderOptimizerContinuationDialogState extends State<DecoderOptimizerContinuationDialog> {
  Map<String, dynamic>? _review;
  bool _busy = false;
  String? _error;
  String get _path => '/decoder-optimizer-fixtures/${widget.sourceId}';
  @override void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() { _busy = true; _review = null; _error = null; });
    try {
      final result = await widget.request('$_path/continuation-review', {});
      if (mounted) setState(() => _review = result);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 660, child: SelectableText(const JsonEncoder.withIndent('  ').convert(record))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _continue() async {
    setState(() { _busy = true; _error = null; });
    try {
      final result = await widget.request('$_path/continue', {'confirmed': true, 'reviewed': _review});
      if (mounted) await _show(result);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _history() async {
    try {
      final records = (await widget.request('$_path/continuations', {}))['records'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(title: const Text('Saved checkpoint continuations'), children: [
        if (records.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No checkpoint continuations saved.')),
        for (final record in records) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
          child: Text('${(record['id'] as String).substring(0, 8)} · completed step ${record['completed_steps']}')),
      ]));
      if (selected != null && mounted) await _show(selected);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
  }
  @override Widget build(BuildContext context) => AlertDialog(title: const Text('Review checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Restore the saved midpoint model, optimizer moments and scheduler counter. Finish the original synthetic training budget in a separate private artifact and compare with the original final model. The source run and checkpoint stay unchanged. This does not establish recovery from an arbitrary interruption or add a text corpus.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text('Restore step ${_review!['source']['checkpoint_step']} · remaining updates: ${_review!['estimates']['optimizer_updates']} · original total: ${_review!['config']['steps']}.'),
        Text(_review!['feasible'] == true ? 'Resources cover conservative continuation reserves.' : 'Checkpoint continuation cannot start.'),
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View checkpoint continuation review'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved checkpoint continuations')),
      TextButton(onPressed: _busy ? null : _load, child: const Text('Refresh continuation review')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
      if (_review?['feasible'] == true) TextButton(onPressed: _busy ? null : _continue, child: const Text('Continue saved checkpoint')),
    ]);
}
