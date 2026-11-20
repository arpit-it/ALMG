import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_trial_evaluation_dialog.dart';

void main() {
  testWidgets('independent CPU evaluation requires action and shows failed target clearly', (tester) async {
    var calls = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamTrialEvaluationDialog(
      run: const {'id': 'trained', 'revision': 'exact'}, request: (path, body) async {
        calls++; expect(path, '/decoder-stream-training-runs/trained/evaluate');
        expect(body, {'confirmed': true, 'reviewed_revision': 'exact'});
        return {'passed': false, 'evaluation': {
          for (final part in ['validation', 'test']) part: {'windows': 17, 'target_tokens': 250, 'next_token_accuracy': .4, 'loss': 2.0},
        }};
      }))));
    await tester.pumpAndSettle(); expect(calls, 0);
    await tester.tap(find.text('Evaluate saved model on CPU')); await tester.pumpAndSettle();
    expect(calls, 1); expect(find.text('80% accuracy target not met. No release approved.'), findsOneWidget);
    expect(find.textContaining('validation: 17 windows'), findsOneWidget);
  });
}
