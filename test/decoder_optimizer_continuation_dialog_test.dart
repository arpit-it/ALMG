import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_optimizer_continuation_dialog.dart';

Map<String, dynamic> review({bool feasible = true}) => {'revision': 'reviewed', 'source': {'checkpoint_step': 10}, 'config': {'steps': 20}, 'estimates': {'optimizer_updates': 10}, 'feasible': feasible, 'blockers': feasible ? <String>[] : ['Not enough local memory.']};

void main() {
  testWidgets('opening continuation reviews the saved source without starting training', (tester) async {
    final paths = <String>[];
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'source', request: (path, body) async { paths.add(path); return review(); })));
    await tester.pumpAndSettle();
    expect(paths, ['/decoder-optimizer-fixtures/source/continuation-review']);
    expect(find.text('Continue saved checkpoint'), findsOneWidget);
    expect(find.textContaining('remaining updates: 10'), findsOneWidget);
  });
  testWidgets('confirmation sends the reviewed checkpoint and displays a separate saved result', (tester) async {
    Map<String, dynamic>? approval;
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'source', request: (path, body) async {
      if (path.endsWith('/continue')) { approval = body; return {'id': 'new-private-result'}; }
      return review();
    })));
    await tester.pumpAndSettle(); await tester.tap(find.text('Continue saved checkpoint')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(approval?['confirmed'], true); expect(approval?['reviewed'], review());
    expect(approval?['request_id'], matches(RegExp(r'^[a-f0-9]{32}$')));
    expect(find.text('Saved checkpoint continuation'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
  testWidgets('blocked continuation cannot be confirmed', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'source', request: (path, body) async => review(feasible: false))));
    await tester.pumpAndSettle();
    expect(find.text('Continue saved checkpoint'), findsNothing);
    expect(find.text('Not enough local memory.'), findsOneWidget);
  });
  testWidgets('continuation-specific estimates and measured peaks retain their scope', (tester) async {
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'source', request: (path, body) async {
      if (path.endsWith('/continue')) return {'isolated_workflow_measurements': {'elapsed_seconds': 1.25, 'isolated_process_peak_rss_bytes': 200, 'isolated_metal_peak_bytes': 100}};
      final result = review(); result['estimates'] = <String, dynamic>{...Map<String, dynamic>.from(result['estimates'] as Map), ...{'optimizer_work_estimate': {'estimated_seconds': 2.5, 'sample_count': 1}, 'isolated_optimizer_memory': {'isolated_process_peak_rss_bytes': 200, 'isolated_metal_peak_bytes': 100}}}; return result;
    })));
    await tester.pumpAndSettle();
    expect(find.textContaining('Estimated remaining checkpoint work: 2.500 s'), findsOneWidget);
    await tester.tap(find.text('Continue saved checkpoint')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Measured isolated continuation work: 1.250 s.'), findsOneWidget);
    expect(find.textContaining('Measured continuation peaks: RSS 200 bytes'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
  testWidgets('cancel uses the active request token and retains a canceled checkpoint result', (tester) async {
    final completion = Completer<Map<String, dynamic>>();
    String? active; String? canceled;
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'source', request: (path, body) async {
      if (path.endsWith('/continue')) { active = body['request_id'] as String; return completion.future; }
      if (path.endsWith('/cancel-continuation')) { canceled = body['request_id'] as String; return {'cancel_requested': true}; }
      return review();
    })));
    await tester.pumpAndSettle(); await tester.tap(find.text('Continue saved checkpoint')); await tester.pump();
    await tester.tap(find.text('Cancel running continuation')); await tester.pump();
    expect(canceled, active); expect(find.textContaining('Waiting for the next safe optimizer boundary'), findsOneWidget);
    completion.complete({'status': 'canceled', 'completed_steps': 12}); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('Continuation canceled at optimizer step 12.'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    expect(find.text('Cancel running continuation'), findsNothing);
  });
  testWidgets('retained partial resume reviews the partial endpoint and restores its saved update', (tester) async {
    final paths = <String>[]; Map<String, dynamic>? approval;
    await tester.pumpWidget(MaterialApp(home: DecoderOptimizerContinuationDialog(sourceId: 'parent', partialId: 'partial', request: (path, body) async {
      paths.add(path);
      if (path.endsWith('/resume')) { approval = body; return {'status': 'completed', 'completed_steps': 20}; }
      final result = review(); result['restore_step'] = 11; result['resume_from'] = {'record_id': 'partial'}; result['estimates'] = {'optimizer_updates': 9}; return result;
    })));
    await tester.pumpAndSettle();
    expect(paths, ['/decoder-optimizer-continuations/partial/resume-review']);
    expect(find.textContaining('Restore step 11 · remaining updates: 9'), findsOneWidget);
    await tester.tap(find.text('Resume retained checkpoint')); await tester.pump(); await tester.pump(const Duration(milliseconds: 300));
    expect(paths.last, '/decoder-optimizer-continuations/partial/resume'); expect(approval?['confirmed'], true);
    expect((approval?['reviewed'] as Map)['restore_step'], 11);
    expect(find.textContaining('Continuation completed at optimizer step 20.'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
  });
}
