import 'dart:convert';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_archive_import_dialog.dart';

void main() {
  testWidgets('archive selection needs confirmation and imported preview preserves exact prompt', (tester) async {
    var calls = 0;
    final record = {'id': 'imported', 'source_name': 'private.zip', 'previews': <dynamic>[]};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamArchiveImportDialog(
      chooseFile: () async => XFile.fromData(utf8.encode('archive'), name: 'private.zip'),
      request: (path, body) async {
        calls++;
        if (path == '/decoder-stream-imports') { expect(body['confirmed'], true); return record; }
        if (path.endsWith('/read')) return record;
        expect(body['prompt'], ' aaaa '); expect(body['confirmed'], true);
        return {'completion': 'private output', 'generated_token_ids': [1]};
      }))));
    await tester.pumpAndSettle(); expect(calls, 0);
    await tester.tap(find.text('Choose streamed archive ZIP')); await tester.pumpAndSettle(); expect(calls, 0);
    await tester.tap(find.text('Confirm private streamed import')); await tester.pumpAndSettle(); expect(calls, 1);
    await tester.enterText(find.byType(TextField), ' aaaa ');
    await tester.tap(find.text('Generate imported-model preview')); await tester.pumpAndSettle(); expect(calls, 3);
    expect(find.text('private output'), findsOneWidget);
  });
}
