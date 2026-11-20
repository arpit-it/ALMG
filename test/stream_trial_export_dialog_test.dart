import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_trial_export_dialog.dart';

void main() {
  testWidgets('export binds reviewed files and cancelling destination creates no archive', (tester) async {
    var calls = 0;
    var choices = 0;
    var writes = 0;
    final review = {'revision': 'review', 'files': <String, dynamic>{}};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamTrialExportDialog(
      run: const {'id': 'a123456789', 'revision': 'run'},
      choosePath: (name) async => choices++ == 0 ? null : '/tmp/private.zip',
      saveBytes: (bytes, path) async { writes++; expect(utf8.decode(bytes), 'archive'); expect(path, '/tmp/private.zip'); },
      request: (path, body) async {
        calls++;
        if (path.endsWith('/export-review')) return review;
        expect(body['approved_review'], review); expect(body['reviewed_revision'], 'run'); expect(body['confirmed'], true);
        return {'data': base64Encode(utf8.encode('archive'))};
      }))));
    await tester.pumpAndSettle(); expect(calls, 0);
    await tester.tap(find.text('Review private export')); await tester.pumpAndSettle();
    await tester.tap(find.text('Choose private ZIP destination')); await tester.pumpAndSettle(); expect(calls, 1); expect(writes, 0);
    await tester.tap(find.text('Choose private ZIP destination')); await tester.pumpAndSettle(); expect(calls, 2); expect(writes, 1);
    expect(find.text('Private ZIP saved: /tmp/private.zip'), findsOneWidget);
  });
}
