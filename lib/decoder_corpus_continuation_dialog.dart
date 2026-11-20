import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';

class DecoderCorpusContinuationDialog extends StatefulWidget {
  const DecoderCorpusContinuationDialog({super.key, required this.sourceId, this.partialId, required this.request});
  final String sourceId;
  final String? partialId;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderCorpusContinuationDialog> createState() => _DecoderCorpusContinuationDialogState();
}
class _DecoderCorpusContinuationDialogState extends State<DecoderCorpusContinuationDialog> {
  Map<String, dynamic>? _review;
  bool _busy = false;
  bool _running = false;
  bool _cancelPending = false;
  String? _requestId;
  String? _error;
  bool get _partial => widget.partialId != null;
  String get _path => _partial ? '/decoder-corpus-continuations/${widget.partialId}' : '/decoder-corpus-optimizer-runs/${widget.sourceId}';
  Future<void> _perform(Future<void> Function() action) async {
    setState(() { _busy = true; _error = null; });
    try { await action(); } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _load() => _perform(() async {
    setState(() => _review = null);
    final review = await widget.request('$_path/${_partial ? 'resume-review' : 'continuation-review'}', {});
    if (mounted) setState(() => _review = review);
  });
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved corpus checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 650, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(record['status'] == 'canceled'
        ? 'Corpus continuation canceled at update ${record['completed_steps']}. Private model, optimizer state and counter retained; no final reference match is claimed.'
        : 'Restored update ${record['restored_step']} · finished update ${record['completed_steps']} · reference weight difference ${record['reference_parameter_max_error']}.'),
      Text('Generated text: ${record['generated_text']}'),
      const Text('Separate private result; the original corpus run is preserved. No model release or broader language-quality acceptance is established.'),
      if (record['isolated_workflow_measurements'] case final Map measured) ...[
        Text('Measured isolated corpus recovery time: ${(measured['elapsed_seconds'] as num).toStringAsFixed(3)} s.'),
        Text('Measured recovery-worker peak RSS: ${measured['isolated_process_peak_rss_bytes']} bytes · Metal peak: ${measured['isolated_metal_peak_bytes']} bytes.'),
        const Text('Fresh-worker peaks include runtime and lineage overhead. Timing covers imports/admission, restore, remaining updates, evaluation/state saving and CPU inference; parent launch and queue/approval waits are excluded. No reference retraining trajectory or large-model feasibility claim.'),
      ],
      SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
    ])), actions: [
      if (record['status'] == 'canceled' && record['id'] is String) TextButton(onPressed: () => showDialog<void>(context: context, builder: (_) => DecoderCorpusContinuationDialog(sourceId: widget.sourceId, partialId: record['id'] as String, request: widget.request)), child: const Text('Review retained corpus partial resume')),
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _continue() => _perform(() async {
    final random = Random.secure();
    final token = List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
    setState(() { _running = true; _cancelPending = false; _requestId = token; });
    try {
      final record = await widget.request('$_path/${_partial ? 'resume' : 'continue'}', {'confirmed': true, 'reviewed': _review, 'request_id': token});
      if (mounted) { setState(() { _running = false; _requestId = null; }); await _show(record); }
    } finally { if (mounted) setState(() { _running = false; _requestId = null; }); }
  });
  Future<void> _cancel() async {
    final token = _requestId;
    if (token == null || !_running || _cancelPending) return;
    setState(() { _cancelPending = true; _error = null; });
    try { await widget.request('$_path/${_partial ? 'cancel-resume' : 'cancel-continuation'}', {'confirmed': true, 'request_id': token}); }
    catch (error) { if (mounted) setState(() { _cancelPending = false; _error = '$error'; }); }
  }
  Future<void> _history() => _perform(() async {
    final result = await widget.request('/decoder-corpus-optimizer-runs/${widget.sourceId}/continuations', {});
    if (!mounted) return;
    setState(() => _busy = false);
    final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Saved corpus checkpoint continuations'), children: [
        if ((result['records'] as List).isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No corpus continuations saved for this run.')),
        for (final record in result['records'] as List) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
          child: Text('${(record['id'] as String).substring(0, 8)} · ${record['status'] ?? 'completed'} · restored ${record['restored_step']} → ${record['completed_steps']}')),
      ]));
    if (selected != null && mounted) await _show(selected);
  });
  @override Widget build(BuildContext context) => AlertDialog(title: Text(_partial ? 'Review retained corpus partial resume' : 'Review corpus checkpoint continuation'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(_partial ? 'Restore this retained canceled model in one isolated worker, FP32 moments and actual saved counter. Complete only the remaining original updates with the original configuration, preserving all ancestors. Resume cancellation retains another private partial; each further resume requires a new review. Arbitrary OS interruption recovery remains unverified.' : 'Restore the saved midpoint model, FP32 optimizer moments and scheduler counter. Complete only the remaining original updates using the original corpus windows and precision settings, then compare with the saved final model. Run in one isolated worker and save a new private model, tokenizer and optimizer state. Original artifacts stay unchanged. Cancel requests stop between optimizer updates and retain private partial model/state. Retained partial resume requires separate approval; arbitrary interrupted-run recovery remains unverified.'),
      if (_busy) const LinearProgressIndicator(),
      if (_running && _cancelPending) const Text('Cancellation requested. Waiting for a safe optimizer-update boundary and retained result.'),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text('Restore update ${_review!['restore_step']} · remaining updates ${_review!['estimates']['optimizer_updates']}.'),
        Text(_review!['feasible'] == true ? 'Resources cover corpus continuation reserves.' : 'Corpus continuation cannot start.'),
        if (_review!['estimates']['isolated_continuation_memory'] case final Map memory)
          Text('Compatible recovery peaks: RSS ${memory['isolated_process_peak_rss_bytes']} bytes · Metal ${memory['isolated_metal_peak_bytes']} bytes. Calculated floor: ${memory['calculated_memory_floor_bytes']} bytes; reserves never fall below the original calculation.'),
        if (_review!['estimates']['corpus_continuation_work_estimate'] case final Map work)
          Text('Estimated remaining recovery work: ${(work['estimated_seconds'] as num).toStringAsFixed(3)} s from ${work['sample_count']} compatible completed run(s). Exact restored source/update only; canceled samples excluded.')
        else const Text('Remaining recovery estimate unavailable: complete a compatible restored-source run first.'),
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View corpus continuation review'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      if (_running) TextButton(onPressed: _cancelPending ? null : _cancel, child: const Text('Cancel corpus continuation')),
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved corpus checkpoint continuations')),
      TextButton(onPressed: _busy ? null : _load, child: Text(_partial ? 'Review retained corpus resume resources' : 'Review corpus continuation resources')),
      if (_review?['feasible'] == true) TextButton(onPressed: _busy ? null : _continue, child: Text(_partial ? 'Confirm resume retained corpus partial' : 'Confirm continue corpus checkpoint')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
