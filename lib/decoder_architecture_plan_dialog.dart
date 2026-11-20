import 'dart:convert';
import 'package:flutter/material.dart';

class DecoderArchitecturePlanDialog extends StatefulWidget {
  const DecoderArchitecturePlanDialog({super.key, required this.request});
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderArchitecturePlanDialog> createState() => _DecoderArchitecturePlanDialogState();
}

class _DecoderArchitecturePlanDialogState extends State<DecoderArchitecturePlanDialog> {
  static const defaults = {'layers': 1, 'hidden_size': 8, 'attention_heads': 1, 'head_dim': 8, 'feed_forward_size': 16, 'context_length': 16, 'vocab_size': 64, 'seed': 7, 'batch_size': 4};
  static const labels = {'layers': 'Layers', 'hidden_size': 'Hidden width', 'attention_heads': 'Attention heads', 'head_dim': 'Head dimension', 'feed_forward_size': 'Feed-forward width', 'context_length': 'Context tokens', 'vocab_size': 'Vocabulary IDs', 'seed': 'Seed', 'batch_size': 'Planning batch size'};
  final _fields = {for (final entry in defaults.entries) entry.key: TextEditingController(text: '${entry.value}')};
  Map<String, dynamic>? _review;
  Map<String, dynamic>? _saved;
  String? _error;
  bool _busy = false;
  String _preset = 'Tiny single-layer';
  @override void dispose() { for (final field in _fields.values) { field.dispose(); } super.dispose(); }
  Map<String, dynamic> get _config => {
    for (final entry in _fields.entries) entry.key: int.tryParse(entry.value.text),
    'position_embedding': 'learned_absolute', 'normalization': 'layer_norm_no_affine', 'activation': 'relu', 'initialization': 'normal_0.02',
  };
  void _usePreset(String value) {
    final values = {...defaults};
    if (value == 'Two-layer / two-head') values.addAll({'layers': 2, 'hidden_size': 16, 'attention_heads': 2, 'head_dim': 8, 'feed_forward_size': 32, 'context_length': 32, 'vocab_size': 128});
    if (value == 'Four-layer / four-head') values.addAll({'layers': 4, 'hidden_size': 64, 'attention_heads': 4, 'head_dim': 16, 'feed_forward_size': 256, 'context_length': 128, 'vocab_size': 512});
    setState(() { _preset = value; for (final entry in values.entries) { _fields[entry.key]!.text = '${entry.value}'; } _review = null; _saved = null; _error = null; });
  }
  Future<void> _calculate() async {
    setState(() { _busy = true; _error = null; _review = null; _saved = null; });
    try {
      final value = await widget.request('/decoder-architecture-plans/review', {'config': _config});
      if (mounted) setState(() { _review = value; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  Future<void> _save() async {
    setState(() { _busy = true; _error = null; });
    try {
      final value = await widget.request('/decoder-architecture-plans/save', {'confirmed': true, 'reviewed': _review});
      if (mounted) setState(() { _saved = value; _busy = false; });
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  Future<void> _history() async {
    setState(() { _busy = true; _error = null; });
    try {
      final plans = (await widget.request('/decoder-architecture-plans/list', {'confirmed': true}))['plans'] as List;
      if (!mounted) return;
      setState(() => _busy = false);
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(title: const Text('Saved decoder architecture plans'), children: [
        if (plans.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved architecture plans.')),
        for (final plan in plans) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(plan as Map)),
          child: Text('${(plan['id'] as String).substring(0, 8)} · ${plan['review']['calculated_parameter_count']} planned parameters')),
      ]));
      if (selected != null && mounted) { setState(() {
        _saved = selected; _review = Map<String, dynamic>.from(selected['review'] as Map);
        for (final entry in _fields.entries) { entry.value.text = '${_review!['config'][entry.key]}'; }
        _error = null;
      }); }
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Decoder architecture plan'), scrollable: true,
    content: SizedBox(width: 680, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Plan only: no weights are allocated and no model execution or training is available from this plan. '
        'Validate dimensions and calculate parameter and memory estimates before allocation. This version plans bias-free dense layers, untied embeddings/head, learned absolute positions, parameter-free LayerNorm, ReLU and normal(0, 0.02) initialization.'),
      DropdownButton<String>(value: _preset, items: [for (final name in ['Tiny single-layer', 'Two-layer / two-head', 'Four-layer / four-head']) DropdownMenuItem(value: name, child: Text(name))], onChanged: _busy ? null : (value) { if (value != null) _usePreset(value); }),
      Wrap(spacing: 12, runSpacing: 8, children: [for (final entry in _fields.entries) SizedBox(width: 200, child: entry.key == 'attention_heads'
        ? Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('Attention heads'), DropdownButton<int>(isExpanded: true,
          value: int.tryParse(entry.value.text), items: [for (var count = 1; count <= 8; count++) DropdownMenuItem(value: count, child: Text('$count heads'))],
          onChanged: _busy ? null : (value) { if (value != null) setState(() { entry.value.text = '$value'; _review = null; _saved = null; }); },
        )]) : TextField(
        controller: entry.value, enabled: !_busy, keyboardType: TextInputType.number, decoration: InputDecoration(labelText: labels[entry.key]),
        onChanged: (_) => setState(() { _review = null; _saved = null; }),
      ))]),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text('Calculated parameters: ${_review!['calculated_parameter_count']}'),
        Text('FP32 weights: ${_review!['estimates']['weight_bytes']} bytes · training layout estimate: ${_review!['estimates']['training_layout_bytes']} bytes'),
        const Text('Calculated, not measured. Training estimate includes FP32 gradients, two Adam moments and an activation layout. It excludes kernel workspace, allocator and runtime memory; it is not a feasibility guarantee.'),
        if (_saved != null) Text('Saved architecture plan: ${(_saved!['id'] as String).substring(0, 8)}'),
        ExpansionTile(title: const Text('View architecture plan record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_saved ?? _review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved architecture plans')),
      TextButton(onPressed: _busy ? null : _calculate, child: const Text('Review architecture estimate')),
      if (_review != null) TextButton(onPressed: _busy ? null : _save, child: const Text('Save reviewed architecture plan')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
