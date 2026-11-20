import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/generated_trial_feasibility_dialog.dart';

void main() {
  testWidgets('factory handoff has its own final approval', (tester) async {
    await tester.pumpWidget(MaterialApp(home: GeneratedTrialFeasibilityDialog(report: {
      'feasible': true, 'hardware': <String, dynamic>{}, 'estimates': <String, dynamic>{}, 'blockers': <String>[],
      'factory': {'job_id': 'fixture'},
    })));
    expect(find.text('Approve factory decoder trial'), findsOneWidget);
    expect(find.text('View factory hardware record'), findsOneWidget);
    expect(find.text('Approve generated decoder trial'), findsNothing);
  });
  testWidgets('checkpoint resume has its own final approval', (tester) async {
    await tester.pumpWidget(MaterialApp(home: GeneratedTrialFeasibilityDialog(report: {
      'feasible': true, 'hardware': <String, dynamic>{}, 'estimates': <String, dynamic>{}, 'blockers': <String>[],
      'resume': {'checkpoint': {'completed_steps': 50}},
    })));
    expect(find.text('Approve saved trial resume'), findsOneWidget);
    expect(find.text('View resume hardware record'), findsOneWidget);
    expect(find.textContaining('50 completed steps'), findsOneWidget);
    expect(find.text('Approve generated decoder trial'), findsNothing);
  });
  testWidgets('reviewed local data has distinct approval and tokenizer/window scope', (tester) async {
    await tester.pumpWidget(MaterialApp(home: GeneratedTrialFeasibilityDialog(report: {
      'feasible': true, 'hardware': <String, dynamic>{}, 'estimates': <String, dynamic>{}, 'blockers': <String>[],
      'dataset': {'vocabulary_size': 256, 'window_counts': {'train': 20}},
    })));
    expect(find.text('Approve reviewed dataset decoder trial'), findsOneWidget);
    expect(find.text('Approve generated decoder trial'), findsNothing);
    expect(find.textContaining('256 tokens and 20 training windows'), findsOneWidget);
  });
  testWidgets('generated decoder hardware blockers hide training approval', (tester) async {
    for (final feasible in [false, true]) {
      await tester.pumpWidget(MaterialApp(home: GeneratedTrialFeasibilityDialog(report: {
        'feasible': feasible, 'hardware': <String, dynamic>{}, 'estimates': <String, dynamic>{},
        'blockers': feasible ? <String>[] : ['Metal unavailable'],
      })));
      expect(find.text('Approve generated decoder trial'), feasible ? findsOneWidget : findsNothing);
      expect(find.textContaining('not measured peaks or a duration prediction'), findsOneWidget);
    }
  });
}
