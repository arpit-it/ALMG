import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_architecture_plan_dialog.dart';

void main() {
  testWidgets('fresh planned model requires separate confirmation and reports forward-only scope', (tester) async {
    var initializations = 0;
    final review = {'config': <String, dynamic>{}, 'calculated_parameter_count': 8704, 'estimates': {'weight_bytes': 34816, 'training_layout_bytes': 466944}};
    final saved = {'id': 'a123456789', 'review': review};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DecoderArchitecturePlanDialog(request: (path, body) async {
      if (path.endsWith('/review')) return review;
      if (path.endsWith('/save')) return saved;
      initializations++; expect(body['confirmed'], true); expect(body['reviewed'], saved);
      return {'actual_parameter_count': 8704, 'actual_weight_bytes': 34816, 'forward_shape': [2, 8, 128], 'causal_prefix_max_error': 0, 'reload_cpu_max_error': 0};
    }))));
    await tester.pumpAndSettle(); await tester.tap(find.text('Review architecture estimate')); await tester.pumpAndSettle();
    await tester.tap(find.text('Save reviewed architecture plan')); await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Initialize fresh planned model')); await tester.tap(find.text('Initialize fresh planned model')); await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(initializations, 0);
    await tester.tap(find.text('Initialize fresh planned model')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm fresh architecture initialization')); await tester.pumpAndSettle();
    expect(initializations, 1); expect(find.text('Initialized architecture CPU check'), findsOneWidget);
    expect(find.textContaining('Backward execution has not been checked'), findsOneWidget);
  });

  testWidgets('architecture review is read-only and editing invalidates save approval', (tester) async {
    var saves = 0;
    Map<String, dynamic>? review;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DecoderArchitecturePlanDialog(request: (path, body) async {
      if (path.endsWith('/review')) {
        review = {'config': body['config'], 'calculated_parameter_count': 1664, 'estimates': {'weight_bytes': 6656, 'training_layout_bytes': 59392}};
        return review!;
      }
      saves++; expect(body['confirmed'], true); expect(body['reviewed'], review);
      return {'id': 'a123456789', 'review': review};
    }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review architecture estimate')); await tester.pumpAndSettle(); expect(saves, 0);
    expect(find.text('Calculated parameters: 1664'), findsOneWidget);
    await tester.tap(find.text('Save reviewed architecture plan')); await tester.pumpAndSettle(); expect(saves, 1);
    await tester.enterText(find.widgetWithText(TextField, 'Hidden width'), '16'); await tester.pumpAndSettle();
    expect(find.text('Save reviewed architecture plan'), findsNothing);
  });
}
