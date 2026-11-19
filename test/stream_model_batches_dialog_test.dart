import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_model_batches_dialog.dart';

void main() {
  testWidgets('batch inspector pages and resets cursors on split changes', (tester) async {
    final calls = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(reviewed: const {'id': 'fixture'}, request: (path, body) async {
      expect(path, '/decoder-stream-windows/fixture/batch'); calls.add(body);
      return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'inputs': [[65, 66]], 'targets': [[66, 67]],
        'loss_mask': [[1, 1]], 'next_cursor': body['cursor'] == null ? {'revision': 'r', 'split': body['split']} : null};
    }))));
    await tester.pumpAndSettle();
    expect(find.text('1 windows · 2 targets'), findsOneWidget);
    await tester.tap(find.text('Next input batch')); await tester.pumpAndSettle();
    expect(calls.last['cursor'], isNotNull);
    await tester.tap(find.text('First input batch')); await tester.pumpAndSettle();
    expect(calls.last['cursor'], isNull);
    await tester.tap(find.byType(DropdownButton<String>)); await tester.pumpAndSettle();
    await tester.tap(find.text('validation').last); await tester.pumpAndSettle();
    expect(calls.last['split'], 'validation'); expect(calls.last['cursor'], isNull);
  });
  testWidgets('batch inspector allows retry after a binding failure', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(reviewed: const {'id': 'fixture'}, request: (path, body) async {
      if (attempts++ == 0) throw StateError('binding changed');
      return {'rows': 0, 'real_target_tokens': 0, 'sequence_lengths': [], 'next_cursor': null};
    }))));
    await tester.pumpAndSettle(); expect(find.textContaining('binding changed'), findsOneWidget);
    await tester.tap(find.text('Retry input batch')); await tester.pumpAndSettle();
    expect(attempts, 2); expect(find.text('0 windows · 0 targets'), findsOneWidget);
  });
}
