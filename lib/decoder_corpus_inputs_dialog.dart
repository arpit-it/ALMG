import 'dart:convert';
import 'package:flutter/material.dart';

class DecoderCorpusInputsDialog extends StatefulWidget {
  const DecoderCorpusInputsDialog({super.key, required this.initialized, required this.request});
  final Map<String, dynamic> initialized;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderCorpusInputsDialog> createState() => _DecoderCorpusInputsDialogState();
}

class _DecoderCorpusInputsDialogState extends State<DecoderCorpusInputsDialog> {
  Map<String, dynamic>? _dataset, _review;
  int _length = 8;
  bool _busy = false;
  String? _error;
  String get _path => '/decoder-architecture-plans/${widget.initialized['plan_id']}';
  Map<String, dynamic> get _body => {'reviewed': widget.initialized, 'dataset': _dataset, 'sequence_length': _length};
  Future<void> _perform(Future<void> Function() action) async {
    setState(() { _busy = true; _error = null; });
    try { await action(); }
    catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _select() => _perform(() async {
    final result = await widget.request('$_path/corpus-input-datasets', {});
    if (!mounted) return;
    setState(() => _busy = false);
    final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Prepared local text datasets'), children: [
        if ((result['datasets'] as List).isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('Prepare a local text dataset in Training first.')),
        for (final item in result['datasets'] as List) SimpleDialogOption(
          onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(item as Map)),
          child: Text('${(item['id'] as String).substring(0, 8)} · ${item['tokenizer']?['vocabulary_size'] ?? '?'} vocabulary IDs')),
      ]));
    if (selected != null && mounted) setState(() { _dataset = selected; _review = null; });
  });
  Future<void> _load() => _perform(() async {
    setState(() => _review = null);
    final result = await widget.request('$_path/corpus-input-review', _body);
    if (mounted) setState(() => _review = result);
  });
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved text corpus inputs'), scrollable: true,
    content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(record))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _save() => _perform(() async {
    final result = await widget.request('$_path/corpus-input-save', {..._body, 'confirmed': true, 'reviewed_inputs': _review});
    if (mounted) await _show(result);
  });
  Future<void> _history() => _perform(() async {
    final result = await widget.request('$_path/corpus-input-history', {'reviewed': widget.initialized});
    if (!mounted) return;
    setState(() => _busy = false);
    final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Saved corpus input reviews'), children: [
        if ((result['records'] as List).isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No corpus inputs saved for this initialization.')),
        for (final item in result['records'] as List) SimpleDialogOption(
          onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(item as Map)),
          child: Text('${(item['id'] as String).substring(0, 8)} · dataset ${(item['review']['dataset_id'] as String).substring(0, 8)} · sequence ${item['review']['sequence_length']}')),
      ]));
    if (selected != null && mounted) await _show(selected);
  });
  @override Widget build(BuildContext context) => AlertDialog(title: const Text('Review text corpus inputs'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Select a prepared local dataset with reviewed source permissions. Check its tokenizer against this fresh initialization and save private input windows. Saving does not start or approve training. The configurable optimizer does not consume these inputs yet.'),
      Text(_dataset == null ? 'No local text dataset selected.' : 'Selected dataset: ${_dataset!['id']}'),
      TextButton(onPressed: _busy ? null : _select, child: const Text('Choose prepared text dataset')),
      DropdownButton<int>(value: _length, items: const [DropdownMenuItem(value: 4, child: Text('Corpus sequence length 4')), DropdownMenuItem(value: 8, child: Text('Corpus sequence length 8'))],
        onChanged: _busy ? null : (value) => setState(() { _length = value!; _review = null; })),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text(_review!['compatible'] == true ? 'Corpus inputs are compatible for private preparation.' : 'Resolve corpus input blockers.'),
        const Text('Windows stay within individual documents. Padding targets are masked. Sampling weights affect training only; validation and test are retained separately.'),
        for (final part in ['train', 'validation', 'test']) Text('$part: ${_review!['splits'][part]['windows']} windows · ${_review!['splits'][part]['target_tokens']} real target tokens'),
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View text corpus input review'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved corpus input reviews')),
      TextButton(onPressed: _busy || _dataset == null ? null : _load, child: const Text('Check corpus compatibility')),
      if (_review?['compatible'] == true) TextButton(onPressed: _busy ? null : _save, child: const Text('Confirm save private corpus inputs')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
