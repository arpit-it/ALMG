import 'dart:convert';
import 'package:flutter/material.dart';

typedef ModelBatchRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);

class StreamModelBatchesDialog extends StatefulWidget {
  const StreamModelBatchesDialog({super.key, required this.reviewed, required this.request, this.routePrefix = 'decoder-stream-windows', this.allowOptimization = true, this.allowPersistence = false});
  final Map<String, dynamic> reviewed;
  final ModelBatchRequest request;
  final String routePrefix;
  final bool allowOptimization;
  final bool allowPersistence;
  @override State<StreamModelBatchesDialog> createState() => _StreamModelBatchesDialogState();
}

class _StreamModelBatchesDialogState extends State<StreamModelBatchesDialog> {
  String _split = 'train';
  Map<String, dynamic>? _cursor;
  Map<String, dynamic>? _batch;
  String? _error;
  bool _loading = true;
  @override void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() { _loading = true; _batch = null; _error = null; });
    try {
      final batch = await widget.request('/${widget.routePrefix}/${widget.reviewed['id']}/batch', {
        'confirmed': true, 'reviewed': widget.reviewed, 'cursor': _cursor, 'split': _split, 'batch_size': 4,
      });
      if (mounted) setState(() { _batch = batch; _loading = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _loading = false; }); }
  }
  Future<void> _checkOptimization() async {
    final batch = _batch;
    if (!widget.allowOptimization || batch == null || _split != 'train') return;
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Check five masked optimizer steps?'),
      content: const Text('Initialize the tiny registered decoder from new weights and run five SGD updates on this inspected training batch using Metal. '
        'Check that masked target changes do not alter loss/gradients and compare CPU inference. '
        'Evaluate every saved validation/test window in batches of at most sixteen, with padding excluded and metrics weighted by real target tokens. Large splits can take time; interrupted checks must be rerun. Model weights are discarded; only a diagnostic report is saved. No training approval or release is granted.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm five-step optimizer check'))],
    ));
    if (confirmed != true || !mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final report = await widget.request('/${widget.routePrefix}/${widget.reviewed['id']}/optimization-check', {
        'confirmed': true, 'reviewed': widget.reviewed, 'reviewed_batch': batch, 'cursor': _cursor,
      });
      if (!mounted) return;
      setState(() => _loading = false);
      await _showOptimizationReport(report);
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _loading = false; }); }
  }

  Future<void> _showOptimizationReport(Map<String, dynamic> report) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Masked optimizer diagnostic verified'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (report['vocabulary_size'] != null) Text('Learned vocabulary: ${report['vocabulary_size']} IDs · architecture version ${report['model_architecture_version']}'),
          if (report['tokenizer_kind'] == 'unigram') const Text('Full-split Unigram numerical check · no saved model or training approval'),
          if (report['tokenizer_kind'] == 'character_bpe') const Text('Full-split character-BPE numerical check · no saved model or training approval'),
          Text('Training batch loss: ${report['initial_batch_loss']} → ${report['final_batch_loss']}'),
          const Text('Five-step numerical check only. The model was discarded; held-out evaluation does not establish usable model quality.'),
          if (report['evaluation'] == null) const Text('Legacy report: held-out probes cover only the first four windows of each split.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(report)),
        ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
  }

  Future<void> _showPersistenceReport(Map<String, dynamic> report) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Stream model/tokenizer persistence verified'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('${report['vocabulary_size']} IDs · tokenization version ${report['tokenization_version']} · architecture version ${report['architecture_version']}'),
        Text('CPU output difference after reload: ${report['cpu_logit_max_error']}'),
        const Text('Fresh seed-7 weights only, with zero optimizer updates. The private model and exact tokenizer were saved together and reloaded. This establishes no model quality, student-training approval or release.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(report)),
      ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  }

  Future<void> _checkPersistence() async {
    final batch = _batch;
    if (!widget.allowPersistence || batch == null || _split != 'train') return;
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Save a fresh model/tokenizer persistence check?'),
      content: const Text('Save a tiny newly initialized decoder and the exact reviewed streamed tokenizer in a new private folder. Reload both, compare every parameter and CPU output, and check lossless source encoding. '
        'No optimizer update or student training runs. Saved weights are untrained; no model quality or release is approved. Tokenizer pieces and probe text may be private.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm private persistence check'))]));
    if (confirmed != true || !mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final report = await widget.request('/${widget.routePrefix}/${widget.reviewed['id']}/persistence-check', {
        'confirmed': true, 'reviewed': widget.reviewed, 'reviewed_batch': batch, 'cursor': _cursor,
      });
      if (!mounted) return;
      setState(() => _loading = false);
      await _showPersistenceReport(report);
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _loading = false; }); }
  }

  Future<void> _savedPersistenceChecks() async {
    if (!widget.allowPersistence) return;
    try {
      final reports = (await widget.request('/${widget.routePrefix}/${widget.reviewed['id']}/persistence-checks', {'confirmed': true}))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved stream persistence checks'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved persistence checks.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['tokenizer_kind']} · ${report['vocabulary_size']} IDs · untrained')),
        ]));
      if (selected != null && mounted) await _showPersistenceReport(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedOptimizationChecks() async {
    if (!widget.allowOptimization) return;
    try {
      final reports = (await widget.request('/${widget.routePrefix}/${widget.reviewed['id']}/optimization-checks', {'confirmed': true}))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved masked optimizer checks'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved optimizer checks.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['steps']} steps · ${report['padded_positions']} padded positions')),
        ],
      ));
      if (selected != null && mounted) await _showOptimizationReport(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Inspect model input batches'),
    content: SizedBox(width: 720, height: MediaQuery.sizeOf(context).height * .55, child: Column(children: [
      const Text('Read-only inputs, shifted targets and loss masks. Token IDs encode original text and may contain personal information. '
        'Zero padding is storage only and must be ignored using the mask. Source/overlap bindings are rechecked; no training approval is granted.'),
      Row(children: [const Text('Saved split: '), DropdownButton<String>(value: _split,
        items: [for (final split in ['train', 'validation', 'test']) DropdownMenuItem(value: split, child: Text(split))],
        onChanged: _loading ? null : (value) { if (value == null) return; _split = value; _cursor = null; _load(); }),
        const Spacer(), if (_batch != null) Text('${_batch!['rows']} windows · ${_batch!['real_target_tokens']} targets')]),
      Expanded(child: _loading ? const Center(child: CircularProgressIndicator()) : _error != null
        ? SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [Text(_error!), TextButton(onPressed: _load, child: const Text('Retry input batch'))]))
        : SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Sequence lengths: ${_batch?['sequence_lengths']}'),
          ExpansionTile(title: const Text('View arrays, masks and source references'), children: [
            SelectableText(const JsonEncoder.withIndent('  ').convert(_batch)),
          ]),
        ]))),
    ])),
    actions: [Wrap(spacing: 8, runSpacing: 4, alignment: WrapAlignment.end, children: [
      if (widget.allowPersistence && _split == 'train') TextButton(onPressed: _loading || _batch == null ? null : _checkPersistence, child: const Text('Check model/tokenizer persistence')),
      if (widget.allowPersistence) TextButton(onPressed: _loading ? null : _savedPersistenceChecks, child: const Text('Saved persistence checks')),
      if (widget.allowOptimization && _split == 'train') TextButton(onPressed: _loading || _batch == null ? null : _checkOptimization, child: const Text('Check masked optimization')),
      if (widget.allowOptimization) TextButton(onPressed: _loading ? null : _savedOptimizationChecks, child: const Text('Saved optimizer checks')),
      TextButton(onPressed: _loading || _cursor == null ? null : () { _cursor = null; _load(); }, child: const Text('First input batch')),
      TextButton(onPressed: _loading || _batch?['next_cursor'] == null ? null : () {
        _cursor = Map<String, dynamic>.from(_batch!['next_cursor'] as Map); _load();
      }, child: const Text('Next input batch')),
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))])],
  );
}
