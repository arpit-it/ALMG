import 'dart:convert';
import 'dart:typed_data';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

class StreamTrialExportDialog extends StatefulWidget {
  const StreamTrialExportDialog({super.key, required this.run, required this.request, this.choosePath, this.saveBytes});
  final Map<String, dynamic> run;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  final Future<String?> Function(String)? choosePath;
  final Future<void> Function(Uint8List, String)? saveBytes;
  @override State<StreamTrialExportDialog> createState() => _StreamTrialExportDialogState();
}

class _StreamTrialExportDialogState extends State<StreamTrialExportDialog> {
  Map<String, dynamic>? _review;
  bool _busy = false;
  String? _error;
  String? _saved;
  Future<void> _loadReview() async {
    setState(() { _busy = true; _error = null; _review = null; });
    try {
      final review = await widget.request('/decoder-stream-training-runs/${widget.run['id']}/export-review', {'confirmed': true, 'reviewed_revision': widget.run['revision']});
      if (mounted) setState(() { _review = review; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  Future<void> _export() async {
    final review = _review;
    if (review == null) return;
    setState(() { _busy = true; _error = null; });
    try {
      final name = 'private-stream-decoder-${(widget.run['id'] as String).substring(0, 8)}.zip';
      final path = widget.choosePath != null ? await widget.choosePath!(name) : (await getSaveLocation(suggestedName: name,
        acceptedTypeGroups: [const XTypeGroup(label: 'Private decoder ZIP', extensions: ['zip'])]))?.path;
      if (path == null || !mounted) { if (mounted) setState(() => _busy = false); return; }
      final result = await widget.request('/decoder-stream-training-runs/${widget.run['id']}/export', {
        'confirmed': true, 'reviewed_revision': widget.run['revision'], 'approved_review': review,
      });
      final bytes = base64Decode(result['data'] as String);
      if (widget.saveBytes != null) { await widget.saveBytes!(bytes, path); }
      else { await XFile.fromData(bytes, mimeType: 'application/zip', name: name).saveTo(path); }
      if (mounted) setState(() { _saved = path; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Private streamed-model archive'), scrollable: true,
    content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Export a private experimental model, exact tokenizer, passing CPU evaluation and saved prompt/output. '
        'Tokenizer pieces, weights and prompts may contain private information. Source documents and training databases are excluded. '
        'The saved evaluation must pass the 80% target and both evaluation and preview must reproduce before export. '
        'This is a private archive, not a model release. Streamed archives can be imported separately for private CPU preview; archived quality claims remain unverified.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_saved != null) Text('Private ZIP saved: $_saved'),
      if (_review != null) ...[
        const Text('Passing CPU evaluation and saved preview verified. Review the private contents before choosing a destination.'),
        ExpansionTile(title: const Text('View reviewed archive files'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _loadReview, child: const Text('Review private export')),
      if (_review != null) TextButton(onPressed: _busy ? null : _export, child: const Text('Choose private ZIP destination')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
