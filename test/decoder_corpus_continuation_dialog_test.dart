import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_corpus_continuation_dialog.dart';

void main() {
  testWidgets('corpus continuation requires a feasible separate review and explicit confirmation', (tester) async {
    bool feasible = false;
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusContinuationDialog(sourceId: 'source', request: (path, body) async {
      calls.add(path);
      if (path.endsWith('/continue')) {
        expect(body['confirmed'], true); expect((body['reviewed'] as Map)['feasible'], true);
        return {'restored_step': 10, 'completed_steps': 20, 'reference_parameter_max_error': 0, 'generated_text': 'amber birch'};
      }
      return {'feasible': feasible, 'restore_step': 10, 'estimates': {'optimizer_updates': 10}, 'blockers': feasible ? [] : ['Insufficient local memory.']};
    })));
    expect(find.text('Confirm continue corpus checkpoint'), findsNothing);
    await tester.tap(find.text('Review corpus continuation resources')); await tester.pumpAndSettle();
    expect(find.text('Insufficient local memory.'), findsOneWidget);
    expect(find.text('Confirm continue corpus checkpoint'), findsNothing);
    feasible = true;
    await tester.tap(find.text('Review corpus continuation resources')); await tester.pumpAndSettle();
    expect(find.text('Restore update 10 · remaining updates 10.'), findsOneWidget);
    await tester.tap(find.text('Confirm continue corpus checkpoint')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Saved corpus checkpoint continuation'), findsOneWidget);
    expect(find.text('Generated text: amber birch'), findsOneWidget);
    expect(calls.where((path) => path.endsWith('/continue')).length, 1);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
}
