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
    expect((requests.last['settings'] as Map)['schema_version'], 3);
    expect((requests.last['settings'] as Map)['gradient_accumulation_steps'], 2);
    await tester.ensureVisible(find.text('FP32 compute')); await tester.tap(find.text('FP32 compute')); await tester.pumpAndSettle();
    await tester.tap(find.text('Mixed FP16 compute').last); await tester.pumpAndSettle();
    expect(find.text('Train and save optimizer fixture'), findsNothing);
    await tester.tap(find.text('Review optimizer fixture')); await tester.pumpAndSettle();
    expect((requests.last['settings'] as Map)['compute_precision'], 'mixed_float16');
    expect((requests.last['settings'] as Map)['loss_scale'], 128.0);
  });
}
