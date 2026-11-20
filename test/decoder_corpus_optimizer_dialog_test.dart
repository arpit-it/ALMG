import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_corpus_optimizer_dialog.dart';

void main() {
  testWidgets('corpus optimizer consent follows resource review and settings invalidate approval', (tester) async {
    final trained = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusOptimizerDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, corpus: const {'id': 'corpus', 'review': {'sequence_length': 8}}, request: (path, body) async {
      if (path.endsWith('train')) {
        trained.add(body);
        return {'initial_losses': {'train': 2, 'validation': 2, 'test': 2}, 'final_losses': {'train': 1, 'validation': 1.5, 'test': 1.6}, 'generated_text': 'amber birch'};
      }
      return {'feasible': true, 'estimates': {'required_available_memory_bytes': 100, 'required_free_disk_bytes': 200}, 'blockers': []};
    })));
    expect(find.text('Confirm train and save corpus model'), findsNothing);
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsOneWidget);
    await tester.ensureVisible(find.text('Corpus SGD')); await tester.tap(find.text('Corpus SGD')); await tester.pumpAndSettle();
    await tester.tap(find.text('Corpus AdamW').last); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsNothing);
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm train and save corpus model')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(trained.single['confirmed'], true); expect((trained.single['settings'] as Map)['optimizer'], 'adamw');
    expect(find.text('Generated text: amber birch'), findsOneWidget);
    expect(find.textContaining('not isolated training peaks'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('20 corpus optimizer updates')); await tester.tap(find.text('20 corpus optimizer updates')); await tester.pumpAndSettle();
    await tester.tap(find.text('10 corpus optimizer updates').last); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsNothing);
  });
  testWidgets('corpus batch and microbatch changes require a new compatible review', (tester) async {
    final settings = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusOptimizerDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, corpus: const {'id': 'corpus', 'review': {'sequence_length': 8}}, request: (path, body) async {
      final c = Map<String, dynamic>.from(body['settings'] as Map); settings.add(c);
      final feasible = c['batch_size'] == 2 || c['gradient_accumulation_steps'] == 1;
      return {'feasible': feasible, 'estimates': {}, 'blockers': feasible ? [] : ['Two microbatches require two effective rows.']};
    })));
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsOneWidget);
    await tester.ensureVisible(find.text('1 corpus microbatch per update')); await tester.tap(find.text('1 corpus microbatch per update')); await tester.pumpAndSettle();
    await tester.tap(find.text('2 corpus microbatches per update').last); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsNothing);
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(find.text('Two microbatches require two effective rows.'), findsOneWidget);
    expect(find.text('Confirm train and save corpus model'), findsNothing);
    await tester.ensureVisible(find.text('Corpus batch size 1')); await tester.tap(find.text('Corpus batch size 1')); await tester.pumpAndSettle();
    await tester.tap(find.text('Corpus batch size 2').last); await tester.pumpAndSettle();
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsOneWidget);
    expect(settings.last['batch_size'], 2); expect(settings.last['gradient_accumulation_steps'], 2);
  });

  testWidgets('corpus precision selection clears approval and submits fixed loss scaling', (tester) async {
    final settings = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusOptimizerDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, corpus: const {'id': 'corpus', 'review': {'sequence_length': 8}}, request: (path, body) async {
      settings.add(Map<String, dynamic>.from(body['settings'] as Map));
      return {'feasible': true, 'estimates': {}, 'blockers': []};
    })));
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsOneWidget);
    await tester.ensureVisible(find.text('Corpus FP32 compute')); await tester.tap(find.text('Corpus FP32 compute')); await tester.pumpAndSettle();
    await tester.tap(find.text('Corpus mixed FP16 compute').last); await tester.pumpAndSettle();
    expect(find.text('Confirm train and save corpus model'), findsNothing);
    await tester.tap(find.text('Review corpus training resources')); await tester.pumpAndSettle();
    expect(settings.last['compute_precision'], 'mixed_float16'); expect(settings.last['loss_scale'], 128.0);
    expect(find.text('Confirm train and save corpus model'), findsOneWidget);
  });

}
