import 'dart:convert';
import 'dart:math';
import 'decoder_corpus_continuation_dialog.dart';
import 'package:flutter/material.dart';

class DecoderCorpusOptimizerDialog extends StatefulWidget {
  const DecoderCorpusOptimizerDialog({super.key, required this.initialized, required this.corpus, required this.request, this.referenceResumeId, this.trainingResumeId});
  final Map<String, dynamic> initialized, corpus;
  final String? referenceResumeId, trainingResumeId;
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>) request;
  @override State<DecoderCorpusOptimizerDialog> createState() => _DecoderCorpusOptimizerDialogState();
}
class _DecoderCorpusOptimizerDialogState extends State<DecoderCorpusOptimizerDialog> {
  String _optimizer = 'sgd';
  String _precision = 'float32';
  int _steps = 20;
  int _batch = 1;
  int _accumulation = 1;
  bool _busy = false;
  bool _running = false;
  bool _cancelPending = false;
  String? _requestId;
  Map<String, dynamic>? _review;
  String? _error;
  bool get _trainingResume => widget.trainingResumeId != null;
  bool get _resume => widget.referenceResumeId != null || _trainingResume;
  String get _resumeLabel => _trainingResume ? 'recorded training' : 'reference';
  String get _resumePath => '/decoder-corpus-optimizer-runs/${widget.trainingResumeId ?? widget.referenceResumeId}';
  String get _path => '/decoder-architecture-plans/${widget.initialized['plan_id']}';
  Map<String, dynamic> get _settings => {'schema_version': 5, 'optimizer': _optimizer, 'learning_rate': 0.01,
    'schedule': 'warmup_cosine', 'warmup_steps': 2, 'steps': _steps, 'gradient_clip_norm': 1.0,
    'weight_decay': _optimizer == 'adamw' ? 0.01 : 0.0, 'batch_size': _batch,
    'sequence_length': widget.corpus['review']['sequence_length'], 'gradient_accumulation_steps': _accumulation,
    'compute_precision': _precision, 'loss_scale': _precision == 'mixed_float16' ? 128.0 : 1.0};
  Map<String, dynamic> get _body => {'reviewed': widget.initialized, 'corpus': widget.corpus, 'settings': _settings};
  Future<void> _perform(Future<void> Function() action) async {
    setState(() { _busy = true; _error = null; });
    try { await action(); } catch (error) { if (mounted) setState(() => _error = '$error'); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _load() => _perform(() async {
    setState(() => _review = null);
    final result = await widget.request(_resume ? '$_resumePath/${_trainingResume ? 'training' : 'reference'}-resume-review' : '$_path/corpus-optimizer-review', _resume ? {} : _body);
    if (mounted) setState(() => _review = result);
  });
  Future<void> _show(Map<String, dynamic> record) => showDialog<void>(context: context, builder: (context) => AlertDialog(
    title: const Text('Saved corpus optimizer run'), scrollable: true,
    content: SizedBox(width: 650, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (record['status'] == 'canceled') Text('Fresh corpus run canceled in ${record['cancellation_phase']} at update ${record['completed_steps']}. Reference updates: ${record['reference_completed_steps']} · recorded training updates: ${record['recorded_training_updates']}. Private model, FP32 state and counter retained; no completed reference or quality claim.'),
      if (record['training_steps_carried'] != null) Text('Retained training updates: ${record['training_steps_carried']} · new training updates executed: ${record['training_updates_executed']} · reference updates executed: ${record['reference_updates_executed']}. Completed reference reused.')
      else if (record['reference_steps_carried'] != null) Text('Retained reference updates: ${record['reference_steps_carried']} · new reference updates executed: ${record['reference_updates_executed']}. Each recorded training trajectory starts from the original fresh initialization.'),
      for (final part in ['train', 'validation', 'test']) Text('$part loss: ${record['initial_losses'][part]} → ${record['final_losses'][part]}'),
      if ((record['schema_version'] as int? ?? 1) >= 2) Text('Effective batch rows: ${record['effective_batch_rows']} · microbatches per update: ${record['gradient_accumulation_steps']} · full-batch gradient difference: ${record['full_batch_gradient_max_error']}.'),
      if ((record['schema_version'] as int? ?? 1) >= 3) Text('Compute: ${record['compute_precision']} · loss scale: ${record['loss_scale']} · FP32 master weights, gradients and moments. Split losses use the saved FP32 master model.'),
      Text('Generated text: ${record['generated_text']}'),
      const Text('Held-out losses are diagnostics on this small corpus. This private result does not establish language quality or release approval.'),
      if (record['isolated_workflow_measurements'] case final Map measured) ...[
        Text('Measured isolated corpus worker time: ${(measured['elapsed_seconds'] as num).toStringAsFixed(3)} s.'),
        Text('Measured fresh-worker peak RSS: ${measured['isolated_process_peak_rss_bytes']} bytes · Metal peak: ${measured['isolated_metal_peak_bytes']} bytes.'),
        Text(record['training_steps_carried'] != null ? 'Includes worker setup, retained reference/state validation, remaining recorded training updates, checkpoint restore, saving and CPU inference. Completed reference is reused; measurements are excluded from full fresh-run forecasts.' : record['reference_steps_carried'] != null ? 'Includes worker setup, only the remaining reference updates, original recorded training, checkpoints and CPU inference. Separate resume measurements are excluded from fresh-run forecasts.' : 'Includes worker imports/admission, both training trajectories, checkpoints and CPU inference. Excludes parent admission, process launch, queue/approval waits and final measurement publication. Peaks include runtime overhead; unified-memory RSS and Metal may overlap. No large-model feasibility or total wall-time guarantee.'),
      ] else if (record['review'] is Map && record['review']['execution_mode'] == 'fresh_process')
        const Text('Isolated worker measurements were not published; phase samples do not establish isolated peaks.')
      else const Text('Workflow time and memory observations share the backend process; these are not isolated training peaks.'),
      SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
    ])), actions: [
      if (record['id'] is String && record['status'] != 'canceled') TextButton(onPressed: () => showDialog<void>(context: context, builder: (_) => DecoderCorpusContinuationDialog(sourceId: record['id'] as String, request: widget.request)), child: const Text('Review corpus checkpoint continuation')),
      if (record['id'] is String && record['status'] == 'canceled' && record['cancellation_phase'] == 'reference_verification') TextButton(onPressed: () => showDialog<void>(context: context, builder: (_) => DecoderCorpusOptimizerDialog(initialized: widget.initialized, corpus: widget.corpus, request: widget.request, referenceResumeId: record['id'] as String)), child: const Text('Review retained corpus reference resume')),
      if (record['id'] is String && record['status'] == 'canceled' && record['cancellation_phase'] == 'checkpointed_training') TextButton(onPressed: () => showDialog<void>(context: context, builder: (_) => DecoderCorpusOptimizerDialog(initialized: widget.initialized, corpus: widget.corpus, request: widget.request, trainingResumeId: record['id'] as String)), child: const Text('Review retained corpus recorded training resume')),
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  Future<void> _train() => _perform(() async {
    final random=Random.secure();final token=List.generate(16,(_)=>random.nextInt(256).toRadixString(16).padLeft(2,'0')).join();
    setState(() { _running=true;_cancelPending=false;_requestId=token; });
    try {
      final record = await widget.request(_resume ? '$_resumePath/${_trainingResume ? 'training' : 'reference'}-resume' : '$_path/corpus-optimizer-train', {..._body, 'reviewed': _resume ? _review : widget.initialized, 'confirmed': true, 'reviewed_feasibility': _review, 'request_id':token});
      if (mounted) { setState(() { _running=false;_requestId=null; });await _show(record); }
    } finally { if(mounted)setState(() { _running=false;_requestId=null; }); }
  });
  Future<void> _cancel() async {
    final token=_requestId;if(token==null || !_running || _cancelPending)return;
    setState(() { _cancelPending=true;_error=null; });
    try { await widget.request('$_path/corpus-optimizer-cancel',{'confirmed':true,'reviewed_feasibility':_review,'request_id':token}); }
    catch(error) { if(mounted)setState(() { _cancelPending=false;_error='$error'; }); }
  }
  Future<void> _history() => _perform(() async {
    final result = await widget.request('$_path/corpus-optimizer-history', {'reviewed': widget.initialized, 'corpus': widget.corpus});
    if (!mounted) return;
    setState(() => _busy = false);
    final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Saved corpus optimizer runs'), children: [
        if ((result['records'] as List).isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No corpus optimizer runs saved.')),
        for (final record in result['records'] as List) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(record as Map)),
          child: Text('${(record['id'] as String).substring(0, 8)} · ${record['status'] ?? 'completed'} · ${record['review']['config']['optimizer']} · step ${record['completed_steps']}')),
      ]));
    if (selected != null && mounted) await _show(selected);
  });
  @override Widget build(BuildContext context) => AlertDialog(title: Text(_resume ? 'Review retained corpus $_resumeLabel resume' : 'Reviewed corpus optimizer training'), scrollable: true,
    content: SizedBox(width: 640, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (_trainingResume) const Text('Restore the saved recorded-training model, FP32 optimizer moments and actual counter. Reuse the completed reference without retraining it. Execute only the remaining original training updates, preserving or creating the original midpoint checkpoint in new private artifacts. Original configuration and every ancestor stay unchanged. Cancellation retains another private partial and further resume requires new approval. Arbitrary OS/process interruption remains unverified.')
      else if (_resume) const Text('Restore the saved reference model, FP32 optimizer moments and actual counter. Finish its remaining original reference updates, then start the separately recorded checkpointed training trajectory from the original fresh initialization. Preserve the canceled source and save a new private result. Cancellation remains available at update boundaries. Recorded-training resume requires a separate phase-specific approval; arbitrary process interruption remains unverified.')
      else ...[
      const Text('Train fresh initialized weights in one isolated local worker using only these saved, permission-reviewed text windows. FP32 or bounded mixed FP16, one/two effective rows per update, learning rate 0.01, two warmup steps, cosine decay and clipping at 1.0. Save a midpoint checkpoint, restore optimizer/scheduler state and compare with a separate uninterrupted trajectory. Both trajectories execute the selected budget.'),
      DropdownButton<String>(value: _optimizer, items: const [DropdownMenuItem(value: 'sgd', child: Text('Corpus SGD')), DropdownMenuItem(value: 'adamw', child: Text('Corpus AdamW'))],
        onChanged: _busy ? null : (value) => setState(() { _optimizer = value!; _review = null; })),
      DropdownButton<String>(value: _precision, items: const [DropdownMenuItem(value: 'float32', child: Text('Corpus FP32 compute')), DropdownMenuItem(value: 'mixed_float16', child: Text('Corpus mixed FP16 compute'))],
        onChanged: _busy ? null : (value) => setState(() { _precision = value!; _review = null; })),
      const Text('Mixed FP16 uses FP16 matrix products with FP32 normalization/softmax/loss and master weights/moments. Gradients are unscaled by 128 before accumulation and clipping. Conservative FP32 reserves remain; memory savings are not promised.'),
      DropdownButton<int>(value: _steps, items: const [DropdownMenuItem(value: 10, child: Text('10 corpus optimizer updates')), DropdownMenuItem(value: 20, child: Text('20 corpus optimizer updates'))],
        onChanged: _busy ? null : (value) => setState(() { _steps = value!; _review = null; })),
      DropdownButton<int>(value: _batch, items: const [DropdownMenuItem(value: 1, child: Text('Corpus batch size 1')), DropdownMenuItem(value: 2, child: Text('Corpus batch size 2'))],
        onChanged: _busy ? null : (value) => setState(() { _batch = value!; _review = null; })),
      DropdownButton<int>(value: _accumulation, items: const [DropdownMenuItem(value: 1, child: Text('1 corpus microbatch per update')), DropdownMenuItem(value: 2, child: Text('2 corpus microbatches per update'))],
        onChanged: _busy ? null : (value) => setState(() { _accumulation = value!; _review = null; })),
      const Text('Document boundaries and masked padding are preserved. Train/validation/test losses use all saved windows weighted by real target tokens. Microbatch gradients are averaged by real target-token counts before clipping and one optimizer/scheduler update. Two microbatches require two effective rows. Saved midpoint continuation requires separate approval; Cancel stops at optimizer-update boundaries in either phase, retaining the active model/state and any completed reference/checkpoint. Reference-phase partial resume requires separate approval; recorded-training partial resume requires its own approval. Reported split losses evaluate the saved FP32 master model.'),
      ],
      if (_busy) const LinearProgressIndicator(),
      if(_running && _cancelPending)const Text('Cancellation requested. Waiting for a safe phase update boundary and retained result.'),
      if (_error != null) Text(_error!),
      if (_review != null) ...[
        if (_resume) Text('Restore $_resumeLabel update ${_review![_trainingResume ? 'training_resume_from' : 'reference_resume_from']['completed_steps']} · remaining reference updates ${_review!['estimates']['reference_optimizer_updates']} · recorded training updates ${_review!['estimates']['recorded_training_optimizer_updates']}.'),
        Text(_review!['feasible'] == true ? 'Resources cover corpus optimizer reserves.' : 'Corpus optimizer cannot start.'),
        Text('Memory reserve: ${_review!['estimates']['required_available_memory_bytes']} bytes · disk reserve: ${_review!['estimates']['required_free_disk_bytes']} bytes.'),
        if (_resume) ...[
          if (_review!['estimates']['isolated_phase_resume_memory'] case final Map memory) Text('Compatible measured resume peaks: RSS ${memory['isolated_process_peak_rss_bytes']} bytes · Metal ${memory['isolated_metal_peak_bytes']} bytes. Calculated floor: ${memory['calculated_memory_floor_bytes']} bytes; existing reserves never decrease.'),
          if (_review!['estimates']['phase_resume_work_estimate'] case final Map work) Text('Estimated $_resumeLabel resume work: ${(work['estimated_seconds'] as num).toStringAsFixed(3)} s from ${work['sample_count']} compatible completed run(s). Exact retained source, revision, phase and counter only; canceled samples excluded. Includes worker setup and approved remaining work; excludes parent launch and queue/approval waits.')
          else const Text('Resume work estimate unavailable: complete a compatible exact-source phase resume first.'),
        ] else ...[
        if (_review!['estimates']['isolated_corpus_memory'] case final Map memory)
          Text('Compatible measured peaks: RSS ${memory['isolated_process_peak_rss_bytes']} bytes · Metal ${memory['isolated_metal_peak_bytes']} bytes. Calculated floor: ${memory['calculated_memory_floor_bytes']} bytes; the reserve never falls below the original calculation.'),
        if (_review!['estimates']['corpus_work_estimate'] case final Map work)
          Text('Estimated corpus workflow work: ${(work['estimated_seconds'] as num).toStringAsFixed(3)} s from ${work['sample_count']} compatible measured run(s). Heuristic includes both trajectories and worker setup; excludes parent launch and queue/approval waits.')
        else const Text('Corpus workflow estimate unavailable: complete a compatible isolated run first.'),
        ],
        for (final reason in _review!['blockers'] as List) Text(reason as String),
        ExpansionTile(title: const Text('View corpus optimizer review'), children: [SelectableText(const JsonEncoder.withIndent('  ').convert(_review))]),
      ],
    ])), actions: [
      if(_running)TextButton(onPressed:_cancelPending ? null : _cancel,child:const Text('Cancel fresh corpus run')),
      TextButton(onPressed: _busy ? null : _history, child: const Text('Saved corpus optimizer runs')),
      TextButton(onPressed: _busy ? null : _load, child: Text(_resume ? 'Review $_resumeLabel resume resources' : 'Review corpus training resources')),
      if (_review?['feasible'] == true) TextButton(onPressed: _busy ? null : _train, child: Text(_resume ? 'Confirm resume retained corpus $_resumeLabel' : 'Confirm train and save corpus model')),
      TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Close')),
    ]);
}
