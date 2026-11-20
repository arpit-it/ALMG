import 'dart:convert';
import 'package:flutter/material.dart';
import 'architecture_feasibility_dialog.dart';

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
  Future<void> _showInitialization(Map<String, dynamic> record) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Initialized architecture CPU check'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Actual parameters: ${record['actual_parameter_count']} · actual FP32 tensor bytes: ${record['actual_weight_bytes']}'),
        Text('CPU output shape: ${record['forward_shape']} · causal prefix error: ${record['causal_prefix_max_error']} · reload error: ${record['reload_cpu_max_error']}'),
        const Text('Fresh seeded weights only. Synthetic token IDs were used for the CPU forward check. Every parameter and forward output reloaded exactly. '
          'This initialization record covers the CPU forward check only; backward results are separate diagnostics. No optimizer update, model quality, training approval or release is established by initialization. Planned memory estimates remain unmeasured; actual tensor bytes exclude runtime overhead.'),
        ExpansionTile(title: const Text('View initialized architecture record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(record))]),
      ])), actions: [
        TextButton(onPressed: () => _backward(record), child: const Text('Check planned-model backward pass')),
        TextButton(onPressed: () => _backwardHistory(record), child: const Text('Saved backward checks')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  }
  Future<void> _showBackward(Map<String, dynamic> report) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Planned-model backward diagnostic'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Five-step synthetic loss: ${report['initial_loss']} → ${report['final_loss']}'),
        Text('Finite gradients and changed tensors: ${(report['changed_parameter_tensors'] as List).length} / ${report['parameter_tensors']}'),
        Text('CPU/Metal output difference: ${report['cpu_metal_max_error_before']} before · ${report['cpu_metal_max_error_after']} after'),
        if (report['hardware_feasibility'] != null) Text('Saved hardware snapshot: ${report['hardware_feasibility']['hardware']['metal_device']?['device_name'] ?? 'unknown'} · '
          '${report['hardware_feasibility']['precision']} · estimated memory reserve ${report['hardware_feasibility']['estimates']['required_available_memory_bytes']} bytes. This is the recorded snapshot, not current availability.')
        else const Text('Legacy report: no hardware feasibility snapshot was captured.'),
        if (report['diagnostic_measurements'] != null) ...[
          Text('Measured diagnostic time: ${report['diagnostic_measurements']['elapsed_seconds']} seconds · '
            'sampled incremental Metal memory: ${report['diagnostic_measurements']['sampled_incremental_metal_bytes']} bytes.'),
          Text('Estimate comparison: ${report['diagnostic_measurements']['observed_increment_exceeds_estimate'] == true ? 'sampled increment exceeded the estimate' : 'sampled increment stayed within the estimate'}. '
            'Conservative observed GPU budget: ${report['diagnostic_measurements']['conservative_observed_gpu_budget_bytes']} bytes.'),
          if (report['diagnostic_measurements']['isolated_trial_peak_measured'] == true) ...[
            Text('Isolated diagnostic Metal peak: ${report['diagnostic_measurements']['isolated_metal_peak_bytes']} bytes · '
              'process peak RSS: ${report['diagnostic_measurements']['isolated_process_peak_rss_bytes']} bytes.'),
            Text('Peak comparison: ${report['diagnostic_measurements']['observed_peak_exceeds_estimate'] == true ? 'measured Metal peak exceeded the estimate' : 'measured Metal peak stayed within the estimate'}.'),
            const Text('A fresh local process ran only this diagnostic. Metal peak excludes cached buffers and CPU memory. Process peak RSS includes interpreter, source loading and CPU checks; '
              'the two values may overlap in unified memory and are not added. Workflow time excludes interpreter/import startup. No full-training peak or duration prediction is claimed.'),
          ] else const Text('Memory observations share the backend process and may include other work. Samples can miss transient peaks and exclude cached buffers and CPU memory. '
            'Process peak counters are retained without resetting. Diagnostic time includes CPU checks; no isolated trial peak or full-training duration is claimed.'),
        ] else const Text('Legacy report: diagnostic timing and memory samples were not captured.'),
        Text(report['padding_check_applicable'] == true ? 'Masked padding loss and gradients were invariant.' : 'Padding check not applicable to this minimum batch/context; both real targets were retained.'),
        const Text('The initialized model is unchanged. Updated diagnostic weights were discarded; only this report was saved. '
          'Selected CPU finite-difference gradients were checked. This synthetic numerical check establishes no model quality, training approval or release.'),
        ExpansionTile(title: const Text('View backward diagnostic record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(report))]),
      ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  }
  Future<void> _backward(Map<String, dynamic> initialized) async {
    final feasibility = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => ArchitectureFeasibilityDialog(initialized: initialized, request: widget.request));
    if (feasibility == null || !mounted) return;
    setState(() { _busy = true; _error = null; });
    showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const PopScope(canPop: false,
      child: AlertDialog(title: Text('Checking Metal backward pass'), content: SizedBox(height: 48, child: Center(child: CircularProgressIndicator())))));
    try {
      final report = await widget.request('/decoder-architecture-plans/${initialized['plan_id']}/backward-check', {'confirmed': true, 'reviewed': initialized, 'reviewed_feasibility': feasibility});
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); setState(() => _busy = false); await _showBackward(report);
    } catch (error) { if (mounted) {
      Navigator.of(context, rootNavigator: true).pop(); setState(() { _error = error.toString(); _busy = false; });
      await showDialog<void>(context: context, builder: (context) => AlertDialog(title: const Text('Backward check unavailable'), content: Text(error.toString()),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
    } }
  }
  Future<void> _backwardHistory(Map<String, dynamic> initialized) async {
    try {
      final records = (await widget.request('/decoder-architecture-plans/${initialized['plan_id']}/backward-checks', {'confirmed': true}))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(title: const Text('Saved planned-model backward checks'), children: [
        if (!records.any((record) => record['initialization_id'] == initialized['id'])) const Padding(padding: EdgeInsets.all(16), child: Text('No backward checks for this initialized model.')),
        for (final record in records.where((record) => record['initialization_id'] == initialized['id'])) SimpleDialogOption(
          onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)), child: Text('${(record['id'] as String).substring(0, 8)} · five steps · weights discarded')),
      ]));
      if (selected != null && mounted) await _showBackward(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }
  Future<void> _initialize() async {
    final saved = _saved;
    if (saved == null) return;
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Initialize this saved architecture?'),
      content: Text('Allocate ${saved['review']['calculated_parameter_count']} new seeded parameters for this exact saved plan, run a bounded synthetic CPU forward/causality check, and save/reload the private weights. '
        'Resource reserves are checked before allocation. No Qwen or downloaded weights are used. No backward pass, optimization, training approval or release runs.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm fresh architecture initialization'))]));
    if (confirmed != true || !mounted) return;
    setState(() { _busy = true; _error = null; });
    try {
      final record = await widget.request('/decoder-architecture-plans/${saved['id']}/initialize', {'confirmed': true, 'reviewed': saved});
      if (!mounted) return;
      setState(() => _busy = false); await _showInitialization(record);
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  Future<void> _initializedHistory() async {
    final saved = _saved;
    if (saved == null) return;
    setState(() { _busy = true; _error = null; });
    try {
      final records = (await widget.request('/decoder-architecture-plans/${saved['id']}/initializations', {'confirmed': true}))['records'] as List;
      if (!mounted) return;
      setState(() => _busy = false);
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved fresh architecture checks'), children: [
          if (records.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved initialized architectures.')),
          for (final record in records) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
            child: Text('${(record['id'] as String).substring(0, 8)} · ${record['actual_parameter_count']} parameters · untrained')),
        ]));
      if (selected != null && mounted) await _showInitialization(selected);
    } catch (error) { if (mounted) setState(() { _error = error.toString(); _busy = false; }); }
  }
  @override Widget build(BuildContext context) => AlertDialog(
    title: const Text('Decoder architecture plan'), scrollable: true,
    content: SizedBox(width: 680, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Review and save layouts without allocating weights or approving training. Separate confirmations can initialize fresh weights, check CPU forward execution and run a Metal backward diagnostic that discards updated weights. '
        'Validate dimensions and calculate parameter and memory estimates before allocation. This version supports bias-free dense layers, untied embeddings/head, learned absolute positions, parameter-free LayerNorm, ReLU and normal(0, 0.02) initialization.'),
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
        if (_saved != null) Wrap(spacing: 8, children: [
          TextButton(onPressed: _busy ? null : _initialize, child: const Text('Initialize fresh planned model')),
          TextButton(onPressed: _busy ? null : _initializedHistory, child: const Text('Saved architecture initializations')),
        ]),
        ExpansionTile(title: const Text('View architecture plan record'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_saved ?? _review))]),
      ],
    ])), actions: [
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved architecture plans')),
      TextButton(onPressed: _busy ? null : _calculate, child: const Text('Review architecture estimate')),
      if (_review != null) TextButton(onPressed: _busy ? null : _save, child: const Text('Save reviewed architecture plan')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
