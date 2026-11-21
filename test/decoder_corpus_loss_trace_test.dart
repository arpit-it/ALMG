import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_corpus_loss_trace.dart';

void main() {
  testWidgets('loss trace reports saved coverage and actual pre-update counters', (tester) async {
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:DecoderCorpusLossTrace(record:{'step_log':[{'step':10},{'step':11,'batch_loss_before_update':1.25,'target_tokens':7},{'step':12,'batch_loss_before_update':1.1,'target_tokens':9}]}))));
    expect(find.text('Saved losses for 2 of 3 updates'),findsOneWidget);
    await tester.tap(find.text('Per-update training loss'));await tester.pumpAndSettle();
    expect(find.text('Update 11 · loss 1.250000 · 7 target tokens'),findsOneWidget);
    expect(find.text('Update 12 · loss 1.100000 · 9 target tokens'),findsOneWidget);
    expect(find.textContaining('Update 10 ·'),findsNothing);
    expect(find.textContaining('held-out split losses are reported separately'),findsOneWidget);
  });
  testWidgets('legacy histories do not invent losses and reference traces are labeled', (tester) async {
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:DecoderCorpusLossTrace(record:{'step_log':[{'step':1}]}))));
    expect(find.byType(ExpansionTile),findsNothing);
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:DecoderCorpusLossTrace(record:{'cancellation_phase':'reference_verification','step_log':[{'step':1,'batch_loss_before_update':1.0,'target_tokens':8}]}))));
    expect(find.text('Per-update reference loss'),findsOneWidget);
  });
}
