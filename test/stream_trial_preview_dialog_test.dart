import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_trial_preview_dialog.dart';

void main() {
  testWidgets('private preview preserves whitespace and only saves on explicit generate', (tester) async {
    var calls = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamTrialPreviewDialog(
      run: const {'id': 'trained', 'revision': 'exact'}, request: (path, body) async {
        calls++;
        expect(path, '/decoder-stream-training-runs/trained/preview');
        expect(body['confirmed'], true); expect(body['reviewed_revision'], 'exact');
        expect(body['prompt'], ' banana '); expect(body['max_new_tokens'], 12);
        return {'completion': 'private output', 'generated_token_ids': [1, 2]};
      }))));
    await tester.pumpAndSettle(); expect(calls, 0);
    await tester.enterText(find.byType(TextField), ' banana ');
    await tester.tap(find.text('Generate and save private preview')); await tester.pumpAndSettle();
    expect(calls, 1); expect(find.textContaining('private output'), findsOneWidget);
  });
}
