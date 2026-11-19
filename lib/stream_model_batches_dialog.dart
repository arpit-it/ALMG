import 'dart:convert';
import 'package:flutter/material.dart';

typedef ModelBatchRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);

class StreamModelBatchesDialog extends StatefulWidget {
  const StreamModelBatchesDialog({super.key, required this.reviewed, required this.request});
  final Map<String, dynamic> reviewed;
  final ModelBatchRequest request;
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
      final batch = await widget.request('/decoder-stream-windows/${widget.reviewed['id']}/batch', {
        'confirmed': true, 'reviewed': widget.reviewed, 'cursor': _cursor, 'split': _split, 'batch_size': 4,
      });
      if (mounted) setState(() { _batch = batch; _loading = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _loading = false; }); }
  }
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Inspect model input batches'),
    content: SizedBox(width: 720, height: MediaQuery.sizeOf(context).height * .55, child: Column(children: [
      const Text('Read-only inputs, shifted targets and loss masks. Token IDs encode original text and may contain personal information. '
        'Zero padding is storage only and must be ignored using the mask. Source/overlap bindings are rechecked; no model runs or training approval is granted.'),
      Row(children: [const Text('Saved split: '), DropdownButton<String>(value: _split,
        items: [for (final split in ['train', 'validation', 'test']) DropdownMenuItem(value: split, child: Text(split))],
        onChanged: _loading ? null : (value) { if (value == null) return; _split = value; _cursor = null; _load(); }),
        const Spacer(), if (_batch != null) Text('${_batch!['rows']} windows · ${_batch!['real_target_tokens']} targets')]),
      Expanded(child: _loading ? const Center(child: CircularProgressIndicator()) : _error != null
        ? Column(children: [Text(_error!), TextButton(onPressed: _load, child: const Text('Retry input batch'))])
        : SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Sequence lengths: ${_batch?['sequence_lengths']}'),
          ExpansionTile(title: const Text('View arrays, masks and source references'), children: [
            SelectableText(const JsonEncoder.withIndent('  ').convert(_batch)),
          ]),
        ]))),
    ])),
    actions: [TextButton(onPressed: _loading || _cursor == null ? null : () { _cursor = null; _load(); }, child: const Text('First input batch')),
      TextButton(onPressed: _loading || _batch?['next_cursor'] == null ? null : () {
        _cursor = Map<String, dynamic>.from(_batch!['next_cursor'] as Map); _load();
      }, child: const Text('Next input batch')),
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
  );
}
