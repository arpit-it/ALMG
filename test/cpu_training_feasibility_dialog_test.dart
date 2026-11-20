import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/cpu_training_feasibility_dialog.dart';

void main() {
  testWidgets('discarded CPU fit requires its own confirmation', (tester) async {
    var runs = 0;
    await tester.pumpWidget(MaterialApp(home: CpuTrainingFeasibilityDialog(
      report: const {'feasible': true, 'settings': {'allow_repair': false}, 'estimates': <String, dynamic>{}, 'blockers': <String>[]},
      measure: (review) async { runs++; return {'measurements': {'process_peak_rss_bytes': 100}}; },
    )));
    await tester.tap(find.text('Measure discarded CPU fit')); await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel').last); await tester.pumpAndSettle(); expect(runs, 0);
    await tester.tap(find.text('Measure discarded CPU fit')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm discarded CPU trial')); await tester.pumpAndSettle();
    expect(runs, 1); expect(find.text('Discarded CPU resource trial'), findsOneWidget);
  });
  testWidgets('CPU image report has a distinct explicit approval', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CpuTrainingFeasibilityDialog(title: 'CPU image recipe feasibility',
      description: 'CPU image fixture without an accelerator', approvalLabel: 'Approve CPU image training',
      report: {'feasible': true, 'estimates': <String, dynamic>{}, 'blockers': <String>[]},
    )));
    expect(find.text('CPU image recipe feasibility'), findsOneWidget);
    expect(find.text('Approve CPU image training'), findsOneWidget);
    expect(find.text('Approve CPU classifier training'), findsNothing);
  });
  testWidgets('CPU feasibility shows no accelerator requirement and blocks approval when resources fail', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CpuTrainingFeasibilityDialog(report: {
      'feasible': false, 'estimates': {'required_available_memory_bytes': 100, 'required_free_disk_bytes': 200}, 'blockers': ['Not enough CPU memory'],
    })));
    expect(find.textContaining('without Metal or CUDA'), findsOneWidget);
    expect(find.text('Not enough CPU memory'), findsOneWidget);
    expect(find.text('Approve CPU classifier training'), findsNothing);
  });
}
