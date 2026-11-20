import 'dart:async';
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
  testWidgets('live corpus cancel uses the active run token and waits for a retained result', (tester) async {
    final result=Completer<Map<String,dynamic>>();
    String? runToken, cancelToken;
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusContinuationDialog(sourceId:'source',request:(path,body) async {
      if(path.endsWith('/continue')) { runToken=body['request_id'] as String; return result.future; }
      if(path.endsWith('/cancel-continuation')) { cancelToken=body['request_id'] as String; expect(body['confirmed'],true); return {'cancel_requested':true}; }
      return {'feasible':true,'restore_step':10,'estimates':{'optimizer_updates':10},'blockers':[]};
    })));
    await tester.tap(find.text('Review corpus continuation resources')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm continue corpus checkpoint')); await tester.pump();
    expect(find.text('Cancel corpus continuation'),findsOneWidget);
    await tester.tap(find.text('Cancel corpus continuation')); await tester.pump();
    expect(cancelToken,runToken); expect(RegExp(r'^[a-f0-9]{32}$').hasMatch(runToken!),true);
    expect(find.textContaining('Waiting for a safe optimizer-update boundary'),findsOneWidget);
    result.complete({'status':'canceled','restored_step':10,'completed_steps':11,'reference_parameter_max_error':null,'generated_text':'amber birch'});
    await tester.pump(); await tester.pump(const Duration(milliseconds:300));
    expect(find.textContaining('Corpus continuation canceled at update 11'),findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    expect(find.text('Cancel corpus continuation'),findsNothing);
  });

  testWidgets('retained corpus partial has separate review and resume routes', (tester) async {
    final paths=<String>[];
    await tester.pumpWidget(MaterialApp(home: DecoderCorpusContinuationDialog(sourceId:'original',partialId:'partial',request:(path,body) async {
      paths.add(path);
      if(path.endsWith('/resume')) {
        expect(body['confirmed'],true);
        return {'status':'completed','restored_step':12,'completed_steps':20,'reference_parameter_max_error':0,'generated_text':'amber birch'};
      }
      return {'feasible':true,'restore_step':12,'estimates':{'optimizer_updates':8},'blockers':[]};
    })));
    expect(find.text('Confirm resume retained corpus partial'),findsNothing);
    await tester.tap(find.text('Review retained corpus resume resources'));await tester.pumpAndSettle();
    expect(paths.last,'/decoder-corpus-continuations/partial/resume-review');
    expect(find.text('Restore update 12 · remaining updates 8.'),findsOneWidget);
    await tester.tap(find.text('Confirm resume retained corpus partial'));await tester.pump();await tester.pump(const Duration(milliseconds:300));
    expect(paths.last,'/decoder-corpus-continuations/partial/resume');
    expect(find.text('Generated text: amber birch'),findsOneWidget);
    await tester.tap(find.text('Close').last);await tester.pumpAndSettle();
  });

}
