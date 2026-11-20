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
  });
}
