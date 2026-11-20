import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_architecture_plan_dialog.dart';

void main() {
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
