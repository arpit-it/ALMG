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
    expect(approval, {'confirmed': true, 'reviewed': review()});
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
}
