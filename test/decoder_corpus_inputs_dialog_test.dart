import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_corpus_inputs_dialog.dart';

void main() {
  testWidgets('corpus input saving requires compatible review and invalidates on selection changes', (tester) async {
    final calls = <String>[];
    bool compatible = false;
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusInputsDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async {
      calls.add(path);
      if (path.endsWith('datasets')) return {'datasets': [{'id': '12345678dataset', 'tokenizer': {'vocabulary_size': 4}}]};
      if (path.endsWith('save')) { expect(body['confirmed'], true); expect((body['reviewed_inputs'] as Map)['compatible'], true); return {'id': 'saved'}; }
      return {'compatible': compatible, 'splits': {for (final part in ['train', 'validation', 'test']) part: {'windows': 2, 'target_tokens': 9}}, 'blockers': compatible ? [] : ['Review source permissions.']};
    })));
    expect(find.text('Confirm save private corpus inputs'), findsNothing);
    await tester.tap(find.text('Choose prepared text dataset')); await tester.pumpAndSettle();
    await tester.tap(find.text('12345678 · 4 vocabulary IDs')); await tester.pumpAndSettle();
    await tester.tap(find.text('Check corpus compatibility')); await tester.pumpAndSettle();
    expect(find.text('Review source permissions.'), findsOneWidget);
    expect(find.text('Confirm save private corpus inputs'), findsNothing);
    compatible = true;
    await tester.tap(find.text('Check corpus compatibility')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm save private corpus inputs')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Saved text corpus inputs'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Corpus sequence length 8'));
    await tester.tap(find.text('Corpus sequence length 8')); await tester.pumpAndSettle();
    await tester.tap(find.text('Corpus sequence length 4').last); await tester.pumpAndSettle();
    expect(find.text('Confirm save private corpus inputs'), findsNothing);
    expect(calls.where((path) => path.endsWith('save')).length, 1);
  });
}
