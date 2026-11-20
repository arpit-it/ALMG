import 'dart:convert';
import 'package:flutter/material.dart';

class DecoderOptimizerFixtureDialog extends StatefulWidget {
  const DecoderOptimizerFixtureDialog({super.key, required this.initialized, required this.request});
  final Map<String, dynamic> initialized;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderOptimizerFixtureDialog> createState() => _DecoderOptimizerFixtureDialogState();
}

class _DecoderOptimizerFixtureDialogState extends State<DecoderOptimizerFixtureDialog> {
  String _optimizer = 'sgd';
  int _accumulation = 1;
  int _steps = 10;
  int _batch = 2;
  int _length = 8;
  String _precision = 'float32';
  final _rate = TextEditingController(text: '0.01');
  Map<String, dynamic>? _review;
  bool _busy = false;
  String? _error;
  Map<String, dynamic> get _settings => {'schema_version': 5, 'batch_size': _batch, 'sequence_length': _length, 'compute_precision': _precision, 'loss_scale': _precision == 'mixed_float16' ? 128.0 : 1.0, 'gradient_accumulation_steps': _accumulation, 'optimizer': _optimizer, 'learning_rate': double.tryParse(_rate.text),
    'schedule': 'warmup_cosine', 'warmup_steps': 2, 'steps': _steps, 'gradient_clip_norm': 1.0, 'weight_decay': _optimizer == 'adamw' ? 0.01 : 0.0};
  String get _path => '/decoder-architecture-plans/${widget.initialized['plan_id']}';
  @override void dispose() { _rate.dispose(); super.dispose(); }
  Future<void> _load() async {
    setState(() { _busy = true; _review = null; _error = null; });
    try {
      final result = await widget.request('$_path/optimizer-review', {'reviewed': widget.initialized, 'settings': _settings});
      if (mounted) setState(() => _review = result);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved optimizer fixture'), scrollable: true,
    content: SizedBox(width: 660, child: SelectableText(const JsonEncoder.withIndent('  ').convert(record))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _train() async {
    setState(() { _busy = true; _error = null; });
    try {
      final record = await widget.request('$_path/optimizer-train', {'confirmed': true, 'reviewed': widget.initialized, 'settings': _settings, 'reviewed_feasibility': _review});
      if (mounted) await _show(record);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _history() async {
    try {
      final records = (await widget.request('$_path/optimizer-fixtures', {'initialization_id': widget.initialized['id']}))['records'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(title: const Text('Saved optimizer fixtures'), children: [
        if (records.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No optimizer fixtures saved.')),
        for (final record in records) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
          child: Text('${(record['id'] as String).substring(0, 8)} · ${record['optimizer']['optimizer']} · step ${record['completed_steps']}')),
      ]));
      if (selected != null && mounted) await _show(selected);
    } catch (error) { if (mounted) setState(() => _error = '$error'); }
  }
  @override Widget build(BuildContext context) => AlertDialog(title: const Text('Bounded optimizer training fixture'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Train this fresh initialization on generated token IDs for ten or twenty optimizer updates. Save a midpoint model, optimizer moments and scheduler counter, restore them and compare with uninterrupted execution. Retain the trained model privately; original initialization stays unchanged. No text-corpus, large-model or release approval is established.'),
      DropdownButton<String>(value: _optimizer, items: const [DropdownMenuItem(value: 'sgd', child: Text('SGD')), DropdownMenuItem(value: 'adamw', child: Text('AdamW'))],
        onChanged: _busy ? null : (value) => setState(() { _optimizer = value!; _review = null; })),
      DropdownButton<String>(value: _precision, items: const [DropdownMenuItem(value: 'float32', child: Text('FP32 compute')), DropdownMenuItem(value: 'mixed_float16', child: Text('Mixed FP16 compute'))],
        onChanged: _busy ? null : (value) => setState(() { _precision = value!; _review = null; })),
      const Text('Mixed FP16 uses FP16 matrix products, FP32 normalization/softmax/loss and FP32 master weights/moments. Fixed loss scaling at 128 is checked for nonfinite gradients. Conservative FP32 reserves remain; memory savings are not promised.'),
      DropdownButton<int>(value: _accumulation, items: const [DropdownMenuItem(value: 1, child: Text('1 microbatch per update')), DropdownMenuItem(value: 2, child: Text('2 microbatches per update'))],
        onChanged: _busy ? null : (value) => setState(() { _accumulation = value!; _review = null; })),
      DropdownButton<int>(value: _batch, items: const [DropdownMenuItem(value: 1, child: Text('Batch size 1')), DropdownMenuItem(value: 2, child: Text('Batch size 2'))],
        onChanged: _busy ? null : (value) => setState(() { _batch = value!; _review = null; })),
      DropdownButton<int>(value: _length, items: const [DropdownMenuItem(value: 4, child: Text('Sequence length 4')), DropdownMenuItem(value: 8, child: Text('Sequence length 8'))],
        onChanged: _busy ? null : (value) => setState(() { _length = value!; _review = null; })),
      DropdownButton<int>(value: _steps, items: const [DropdownMenuItem(value: 10, child: Text('10 optimizer updates')), DropdownMenuItem(value: 20, child: Text('20 optimizer updates'))],
        onChanged: _busy ? null : (value) => setState(() { _steps = value!; _review = null; })),
      const Text('A separate uninterrupted comparison repeats the selected budget to verify checkpoint recovery. Saved step logs describe only the checkpointed trajectory.'),
      const Text('Selected batch and sequence must fit the initialized plan. Two-way accumulation requires batch size 2. Resource review retains conservative reserves for the full initialized plan.'),
      const Text('Accumulation averages gradients by real target-token count, then clips and updates once. Optimizer/scheduler counters and checkpoint steps count updates, not microbatches.'),
      TextField(controller: _rate, enabled: !_busy, decoration: const InputDecoration(labelText: 'Learning rate (0 to 0.1, exclusive zero)'), onChanged: (_) => setState(() => _review = null)),
      const Text('Metal gradients with FP32 master/NumPy optimizer state; two warmup steps, cosine decay and global gradient clipping at 1.0. This fixture supports at most 16,384 parameters. Cancellation and independent checkpoint continuation are not exposed yet.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        Text(_review!['feasible'] == true ? 'Resources cover calculated optimizer fixture reserves.' : 'Optimizer fixture cannot start.'),
        Text('Optimizer updates: ${_review!['estimates']['optimizer_updates']} · checkpoint step: ${_review!['estimates']['checkpoint_step']}. Batch rows: ${_review!['estimates']['effective_batch_rows']} · sequence length: ${_review!['estimates']['sequence_length']} · targets per update: ${_review!['estimates']['target_tokens_per_update']}. Calculated optimizer-state bytes: ${_review!['estimates']['optimizer_state_bytes']} · accumulation buffer: ${_review!['estimates']['gradient_accumulation_buffer_bytes']} · memory reserve: ${_review!['estimates']['required_available_memory_bytes']} bytes.'),
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View optimizer feasibility record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved optimizer fixtures')),
      TextButton(onPressed: _busy ? null : _load, child: const Text('Review optimizer fixture')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
      if (_review?['feasible'] == true) TextButton(onPressed: _busy ? null : _train, child: const Text('Train and save optimizer fixture')),
    ]);
}
