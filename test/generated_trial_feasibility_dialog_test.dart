import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/generated_trial_feasibility_dialog.dart';

void main() {
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
