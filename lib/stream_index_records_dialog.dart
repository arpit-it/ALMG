import 'dart:convert';
import 'package:flutter/material.dart';

typedef IndexRecordsRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);

class StreamIndexRecordsDialog extends StatefulWidget {
  const StreamIndexRecordsDialog({super.key, required this.indexId, required this.request});
  final String indexId;
  final IndexRecordsRequest request;
  @override
  State<StreamIndexRecordsDialog> createState() => _StreamIndexRecordsDialogState();
}

class _StreamIndexRecordsDialogState extends State<StreamIndexRecordsDialog> {
  String _split = 'all';
  final List<Map<String, dynamic>?> _history = [null];
  int _position = 0;
  bool _historyTrimmed = false;
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _page;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; _page = null; });
    try {
      final page = await widget.request('/decoder-stream-indexes/${widget.indexId}/records', {
        'confirmed': true, 'cursor': _history[_position], 'split': _split, 'limit': 10,
      });
      if (mounted) setState(() { _page = page; _loading = false; });
    } catch (error) {
      if (mounted) setState(() { _error = error.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final records = (_page?['records'] as List?) ?? [];
    return AlertDialog(
      title: const Text('Review indexed local records'),
      content: SizedBox(width: 720, height: MediaQuery.sizeOf(context).height * .55, child: Column(children: [
        const Text('Read-only excerpts. Detected contact details are masked; other personal information may remain. Scores are local heuristics, not meaning or factual accuracy.'),
        Row(children: [const Text('Saved split: '), DropdownButton<String>(value: _split,
          items: [for (final split in ['all', 'train', 'validation', 'test']) DropdownMenuItem(value: split, child: Text(split))],
          onChanged: _loading ? null : (value) { if (value == null) return; _split = value; _history.clear(); _history.add(null); _position = 0; _historyTrimmed = false; _load(); }),
          const Spacer(), Text('${records.length} records shown')]),
        Expanded(child: _loading ? const Center(child: CircularProgressIndicator()) : _error != null
          ? Column(children: [Text(_error!), TextButton(onPressed: _load, child: const Text('Retry record page'))])
          : records.isEmpty ? const Center(child: Text('No records in this split.')) : ListView.builder(itemCount: records.length, itemBuilder: (context, index) {
            final row = Map<String, dynamic>.from(records[index] as Map);
            final metadata = Map<String, dynamic>.from(row)..remove('text_excerpt');
            return Card(child: Padding(padding: const EdgeInsets.all(8), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Line ${row['first_line']} · ${row['split']} · ${row['occurrences']} occurrences · hygiene ${(row['text_hygiene'] as Map)['score']}'),
              SelectableText(row['text_excerpt'] as String),
              if (row['excerpt_truncated'] == true) const Text('Excerpt limited to 512 characters.'),
              Text('${row['privacy_matches']} potential contact details'),
              ExpansionTile(title: const Text('Source details and findings'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(metadata))]),
            ])));
          })),
      ])),
      actions: [
        TextButton(onPressed: _loading || _position == 0 ? null : () { _position--; _load(); }, child: const Text('Previous records')),
        TextButton(onPressed: _loading || _page?['next_cursor'] == null ? null : () {
          _history.removeRange(_position + 1, _history.length);
          _history.add(Map<String, dynamic>.from(_page!['next_cursor'] as Map)); _position++;
          if (_history.length > 50) { _history.removeAt(0); _position--; _historyTrimmed = true; }
          _load();
        }, child: const Text('Next records')),
        TextButton(onPressed: _loading || (_position == 0 && !_historyTrimmed) ? null : () {
          _history.clear(); _history.add(null); _position = 0; _historyTrimmed = false; _load();
        }, child: const Text('First records')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    );
  }
}
