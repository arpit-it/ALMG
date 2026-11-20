import 'dart:async';
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

  testWidgets('isolated corpus measurements and calibrated estimates are labeled separately', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusOptimizerDialog(initialized:const {'id':'init','plan_id':'plan'},corpus:const {'id':'corpus','review':{'sequence_length':8}},request:(path,body) async {
      if(path.endsWith('train')) return {'initial_losses':{'train':2,'validation':2,'test':2},'final_losses':{'train':1,'validation':1.5,'test':1.6},'generated_text':'amber birch','isolated_workflow_measurements':{'elapsed_seconds':.5,'isolated_process_peak_rss_bytes':1000,'isolated_metal_peak_bytes':100}};
      return {'feasible':true,'estimates':{'isolated_corpus_memory':{'isolated_process_peak_rss_bytes':1000,'isolated_metal_peak_bytes':100,'calculated_memory_floor_bytes':1375},'corpus_work_estimate':{'estimated_seconds':.625,'sample_count':1}},'blockers':[]};
    })));
    await tester.tap(find.text('Review corpus training resources'));await tester.pumpAndSettle();
    await tester.ensureVisible(find.textContaining('Estimated corpus workflow work: 0.625 s'));
    expect(find.textContaining('Compatible measured peaks: RSS 1000 bytes'),findsOneWidget);
    await tester.tap(find.text('Confirm train and save corpus model'));await tester.pump();await tester.pump(const Duration(milliseconds:300));
    expect(find.text('Measured isolated corpus worker time: 0.500 s.'),findsOneWidget);
    expect(find.textContaining('these are not isolated training peaks'),findsNothing);
    await tester.tap(find.text('Close').last);await tester.pumpAndSettle();
  });

  testWidgets('fresh run cancellation uses the reviewed token and labels the retained phase', (tester) async {
    final result=Completer<Map<String,dynamic>>();String? active,canceled;
    await tester.pumpWidget(MaterialApp(home:DecoderCorpusOptimizerDialog(initialized:const {'id':'init','plan_id':'plan'},corpus:const {'id':'corpus','review':{'sequence_length':8}},request:(path,body) async {
      if(path.endsWith('train')) { active=body['request_id'] as String;return result.future; }
      if(path.endsWith('cancel')) { canceled=body['request_id'] as String;expect(body['reviewed_feasibility'],isNotNull);return {'cancel_requested':true}; }
      return {'feasible':true,'estimates':{},'blockers':[]};
    })));
    await tester.tap(find.text('Review corpus training resources'));await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm train and save corpus model'));await tester.pump();
    await tester.tap(find.text('Cancel fresh corpus run'));await tester.pump();
    expect(canceled,active);expect(RegExp(r'^[a-f0-9]{32}$').hasMatch(active!),true);
    result.complete({'status':'canceled','schema_version':4,'cancellation_phase':'reference_verification','completed_steps':1,'reference_completed_steps':1,'recorded_training_updates':0,'initial_losses':{'train':2,'validation':2,'test':2},'final_losses':{'train':1.9,'validation':1.9,'test':1.9},'generated_text':'amber birch'});
    await tester.pump();await tester.pump(const Duration(milliseconds:300));
    expect(find.textContaining('Fresh corpus run canceled in reference_verification at update 1'),findsOneWidget);
    expect(find.text('Review corpus checkpoint continuation'),findsNothing);
    await tester.tap(find.text('Close').last);await tester.pumpAndSettle();
  });

  testWidgets('reference resume requires its own review and shows carried versus executed work', (tester) async {
    Map<String,dynamic>? submitted;
    await tester.pumpWidget(MaterialApp(home:DecoderCorpusOptimizerDialog(initialized:const {'id':'init','plan_id':'plan'},corpus:const {'id':'corpus','review':{'sequence_length':8}},referenceResumeId:'retained',request:(path,body) async {
      if(path.endsWith('reference-resume-review'))return {'feasible':true,'reference_resume_from':{'record_id':'retained','completed_steps':2},'estimates':{'reference_optimizer_updates':18,'recorded_training_optimizer_updates':20},'blockers':[]};
      expect(path,'/decoder-corpus-optimizer-runs/retained/reference-resume');submitted=body;
      return {'reference_steps_carried':2,'reference_updates_executed':18,'initial_losses':{'train':2,'validation':2,'test':2},'final_losses':{'train':1,'validation':1.5,'test':1.6},'generated_text':'amber birch'};
    })));
    expect(find.text('Corpus SGD'),findsNothing);
    expect(find.text('Confirm resume retained corpus reference'),findsNothing);
    await tester.tap(find.text('Review reference resume resources'));await tester.pumpAndSettle();
    expect(find.textContaining('Restore reference update 2 · remaining reference updates 18'),findsOneWidget);
    await tester.tap(find.text('Confirm resume retained corpus reference'));await tester.pump();await tester.pump(const Duration(milliseconds:300));
    expect(submitted!['confirmed'],true);expect((submitted!['reviewed'] as Map)['reference_resume_from']['record_id'],'retained');
    expect(find.textContaining('Retained reference updates: 2 · new reference updates executed: 18'),findsOneWidget);
    await tester.tap(find.text('Close').last);await tester.pumpAndSettle();
  });

  testWidgets('recorded training resume requires its own review and shows carried versus executed work', (tester) async {
    Map<String,dynamic>? submitted;
    await tester.pumpWidget(MaterialApp(home:DecoderCorpusOptimizerDialog(initialized:const {'id':'init','plan_id':'plan'},corpus:const {'id':'corpus','review':{'sequence_length':8}},trainingResumeId:'retained',request:(path,body) async {
      if(path.endsWith('training-resume-review'))return {'feasible':true,'training_resume_from':{'record_id':'retained','completed_steps':2},'estimates':{'reference_optimizer_updates':0,'recorded_training_optimizer_updates':18},'blockers':[]};
      expect(path,'/decoder-corpus-optimizer-runs/retained/training-resume');submitted=body;
      return {'training_steps_carried':2,'training_updates_executed':18,'reference_updates_executed':0,'initial_losses':{'train':2,'validation':2,'test':2},'final_losses':{'train':1,'validation':1.5,'test':1.6},'generated_text':'amber birch'};
    })));
    expect(find.text('Corpus SGD'),findsNothing);
    expect(find.text('Confirm resume retained corpus recorded training'),findsNothing);
    await tester.tap(find.text('Review recorded training resume resources'));await tester.pumpAndSettle();
    expect(find.textContaining('Restore recorded training update 2 · remaining reference updates 0'),findsOneWidget);
    await tester.tap(find.text('Confirm resume retained corpus recorded training'));await tester.pump();await tester.pump(const Duration(milliseconds:300));
    expect(submitted!['confirmed'],true);expect((submitted!['reviewed'] as Map)['training_resume_from']['record_id'],'retained');
    expect(find.textContaining('Retained training updates: 2 · new training updates executed: 18'),findsOneWidget);
    await tester.tap(find.text('Close').last);await tester.pumpAndSettle();
  });

  testWidgets('resume reviews distinguish measured peaks and exact-phase work estimates', (tester) async {
    for(final training in [false,true]) {
      final label=training ? 'recorded training' : 'reference';
      await tester.pumpWidget(MaterialApp(home:DecoderCorpusOptimizerDialog(key:ValueKey(label),initialized:const {'id':'init','plan_id':'plan'},corpus:const {'id':'corpus','review':{'sequence_length':8}},referenceResumeId:training ? null : 'retained',trainingResumeId:training ? 'retained' : null,request:(path,body) async => {'feasible':true,training ? 'training_resume_from' : 'reference_resume_from':{'completed_steps':2},'estimates':{'reference_optimizer_updates':training ? 0 : 18,'recorded_training_optimizer_updates':training ? 18 : 20,'isolated_phase_resume_memory':{'isolated_process_peak_rss_bytes':1000,'isolated_metal_peak_bytes':100,'calculated_memory_floor_bytes':1375},'phase_resume_work_estimate':{'estimated_seconds':.625,'sample_count':1}},'blockers':[]})));
      await tester.tap(find.text('Review $label resume resources'));await tester.pumpAndSettle();
      await tester.ensureVisible(find.textContaining('Estimated $label resume work: 0.625 s'));
      expect(find.textContaining('Compatible measured resume peaks: RSS 1000 bytes'),findsOneWidget);
      expect(find.textContaining('Exact retained source, revision, phase and counter only'),findsOneWidget);
      expect(find.textContaining('Corpus workflow estimate unavailable'),findsNothing);
      expect(find.textContaining('Estimated corpus workflow work:'),findsNothing);
    }
  });

}
