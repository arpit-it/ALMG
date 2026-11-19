import 'package:flutter/material.dart';

typedef PrivateDecoderRequest = Future<Map<String, dynamic>> Function(String path, [Map<String, dynamic>? body]);

/// Integrity-checked private CPU preview, separate from training and release.
class PrivateDecoderPage extends StatefulWidget {
  const PrivateDecoderPage({super.key, required this.importId, required this.name, required this.request});

  final String importId;
  final String name;
  final PrivateDecoderRequest request;

  @override
  State<PrivateDecoderPage> createState() => _PrivateDecoderPageState();
}

class _PrivateDecoderPageState extends State<PrivateDecoderPage> {
  final _prompt = TextEditingController();
  Map<String, dynamic>? _record;
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _busy = true; _error = null; _record = null; _result = null; });
    try {
      final record = await widget.request('/decoder-imports/${widget.importId}');
      if (mounted) setState(() => _record = record);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _generate() async {
    if (_busy || _record == null || _prompt.text.trim().isEmpty) return;
    setState(() { _busy = true; _error = null; _result = null; });
    try {
      final result = await widget.request('/decoder-imports/${widget.importId}/preview', {
        'confirmed': true, 'prompt': _prompt.text.trim(), 'max_new_tokens': 12,
      });
      if (mounted) {
        setState(() {
          _result = result;
          final history = [...(_record!['previews'] as List? ?? const []), result];
          _record = {..._record!, 'previews': history.length > 20 ? history.sublist(history.length - 20) : history};
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _prompt.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final previews = _record?['previews'] as List? ?? const [];
    return Scaffold(
      appBar: AppBar(title: const Text('Private decoder preview'), actions: [
        IconButton(tooltip: 'Refresh private decoder', onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        Text(widget.name, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        const Text('Private CPU preview only. Dataset documents are unavailable, so evaluation claims are unverified. Training and release are unavailable.'),
        if (_busy) const LinearProgressIndicator(),
        if (_error != null) SelectableText(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (_record != null) ...[
          const SizedBox(height: 12),
          Text('Tokenizer: ${_record!['tokenizer_format'] == 'almg-utf8-byte-tokenizer-v1' ? 'UTF-8 bytes' : 'Saved word vocabulary'} · Context: ${_record!['config']['context_length']} tokens'),
          const Text('Generate 12 tokens locally using the saved model and tokenizer.'),
        ],
        const SizedBox(height: 16),
        TextField(controller: _prompt, enabled: _record != null && !_busy, maxLength: 4096, minLines: 1, maxLines: 3,
          decoration: const InputDecoration(labelText: 'Prompt', border: OutlineInputBorder())),
        FilledButton(onPressed: _record == null || _busy ? null : _generate, child: const Text('Generate local text')),
        if (_result != null) ...[
          const SizedBox(height: 16),
          const Text('Generated text'),
          SelectableText(_result!['completion'] as String),
        ],
        if (previews.isNotEmpty) ExpansionTile(title: Text('Saved previews (${previews.length})'), children: [
          for (final preview in previews.reversed) ListTile(title: Text(preview['prompt'] as String), subtitle: Text(preview['completion'] as String)),
        ]),
      ]),
    );
  }
}
