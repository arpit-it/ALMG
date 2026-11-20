import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_optimizer_fixture_dialog.dart';

void main() {
  testWidgets('optimizer changes invalidate review and training requires reviewed resources', (tester) async {
    final requests = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerFixtureDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async {
      requests.add(body);
      return {'feasible': true, 'estimates': {'optimizer_state_bytes': 100}, 'blockers': <String>[]};
    })));
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsOneWidget);
    await tester.tap(find.text('SGD')); await tester.pumpAndSettle(); await tester.tap(find.text('AdamW').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['optimizer'], 'adamw');
    await tester.ensureVisible(find.text('1 microbatch per update'));
    await tester.tap(find.text('1 microbatch per update')); await tester.pumpAndSettle();
    await tester.tap(find.text('2 microbatches per update').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['schema_version'], 5);
    expect((requests.last['settings'] as Map)['gradient_accumulation_steps'], 2);
    await tester.ensureVisible(find.text('FP32 compute')); await tester.tap(find.text('FP32 compute')); await tester.pumpAndSettle();
    await tester.tap(find.text('Mixed FP16 compute').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['compute_precision'], 'mixed_float16');
    expect((requests.last['settings'] as Map)['loss_scale'], 128.0);
    await tester.ensureVisible(find.text('Batch size 2')); await tester.tap(find.text('Batch size 2')); await tester.pumpAndSettle();
    await tester.tap(find.text('Batch size 1').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['batch_size'], 1);
    await tester.ensureVisible(find.text('Sequence length 8')); await tester.tap(find.text('Sequence length 8')); await tester.pumpAndSettle();
    await tester.tap(find.text('Sequence length 4').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['sequence_length'], 4);
    await tester.ensureVisible(find.text('10 optimizer updates')); await tester.tap(find.text('10 optimizer updates')); await tester.pumpAndSettle();
    await tester.tap(find.text('20 optimizer updates').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['steps'], 20);
  });
  testWidgets('saved resource observations distinguish measured shared memory from isolated peaks', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerFixtureDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async {
      if (path.endsWith('/optimizer-train')) return {'workflow_measurements': {'elapsed_seconds': 1.25, 'sampled_active_metal_max_bytes': 128}};
      return {'feasible': true, 'estimates': {'optimizer_state_bytes': 100}, 'blockers': <String>[]};
    })));
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    await tester.tap(find.text('Train and save optimizer fixture')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('Measured workflow time: 1.250 s'), findsOneWidget);
    expect(find.textContaining('These are not isolated trial peaks'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
  testWidgets('review labels compatible work estimate separately from measured time and memory', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerFixtureDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async => {
      'feasible': true, 'estimates': {'optimizer_work_estimate': {'estimated_seconds': 5.0, 'sample_count': 2}}, 'blockers': <String>[]
    })));
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect(find.text('Estimated workflow work: 5.000 s from 2 compatible measured run(s).'), findsOneWidget);
    expect(find.textContaining('not a total wall-time guarantee'), findsOneWidget);
    expect(find.textContaining('Measured workflow time:'), findsNothing);
  });
  testWidgets('fresh-worker observations display isolated peaks instead of shared-process labels', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerFixtureDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async {
      if (path.endsWith('/optimizer-train')) return {'isolated_workflow_measurements': {'elapsed_seconds': 1.5, 'isolated_process_peak_rss_bytes': 200, 'isolated_metal_peak_bytes': 100}};
      return {'feasible': true, 'estimates': {}, 'blockers': <String>[]};
    })));
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    await tester.tap(find.text('Train and save optimizer fixture')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Measured isolated worker time: 1.500 s.'), findsOneWidget);
    expect(find.textContaining('Measured fresh-worker peak RSS: 200 bytes'), findsOneWidget);
    expect(find.textContaining('RSS is a process-lifetime high-water mark'), findsNothing);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
}
