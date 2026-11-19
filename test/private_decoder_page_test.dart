import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/private_decoder_page.dart';

void main() {
  testWidgets('private library preview sends only confirmed import inference and retains history', (tester) async {
    final calls = <String>[];
    Future<Map<String, dynamic>> request(String path, [Map<String, dynamic>? body]) async {
      calls.add(path);
      if (body == null) {
        return {'tokenizer_format': 'almg-utf8-byte-tokenizer-v1', 'config': {'context_length': 16}, 'previews': []};
      }
      expect(body, {'confirmed': true, 'prompt': 'zz', 'max_new_tokens': 12});
      return {'prompt': 'zz', 'completion': 'a a a a a a ', 'import_id': 'fixture'};
    }
    await tester.pumpWidget(MaterialApp(home: PrivateDecoderPage(importId: 'fixture', name: 'private.zip', request: request)));
    await tester.pumpAndSettle();
    expect(find.textContaining('evaluation claims are unverified'), findsOneWidget);
    expect(find.textContaining('Context: 16 tokens'), findsOneWidget);
    expect(find.text('Release'), findsNothing);
    await tester.enterText(find.byType(TextField), 'zz');
    await tester.tap(find.text('Generate local text'));
    await tester.pumpAndSettle();
    expect(calls, ['/decoder-imports/fixture', '/decoder-imports/fixture/preview']);
    expect(find.text('Generated text'), findsOneWidget);
    expect(find.text('Saved previews (1)'), findsOneWidget);
    expect(find.text('a a a a a a '), findsOneWidget);
  });

  testWidgets('integrity failure leaves inference disabled until a valid refresh', (tester) async {
    Future<Map<String, dynamic>> request(String path, [Map<String, dynamic>? body]) async {
      throw const FormatException('Imported decoder integrity changed.');
    }
    await tester.pumpWidget(MaterialApp(home: PrivateDecoderPage(importId: 'fixture', name: 'broken.zip', request: request)));
    await tester.pumpAndSettle();
    expect(find.textContaining('integrity changed'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
  });
}
