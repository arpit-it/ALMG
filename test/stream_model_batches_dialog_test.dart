import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_model_batches_dialog.dart';

void main() {
  testWidgets('optimizer execution requires separate confirmation', (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(reviewed: const {'id': 'fixture'}, request: (path, body) async {
      calls.add(path);
      if (path.endsWith('/optimization-check')) {
        expect(body['confirmed'], isTrue); expect(body['reviewed_batch'], isNotNull);
        return {'initial_batch_loss': 2.0, 'final_batch_loss': 1.0, 'model_saved': false};
      }
      return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'next_cursor': null};
    }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    expect(find.textContaining('Evaluate every saved validation/test window'), findsOneWidget);
    expect(calls.length, 1);
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(calls.length, 1);
    await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm five-step optimizer check')); await tester.pumpAndSettle();
    expect(calls.last.endsWith('/optimization-check'), isTrue);
    expect(find.text('Masked optimizer diagnostic verified'), findsOneWidget);
    expect(find.textContaining('Legacy report:'), findsOneWidget);
  });

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
    expect(find.text('Check masked optimization'), findsNothing);
  });
  testWidgets('learned IDs use their own read-only route without optimizer controls', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: const {'id': 'learned'}, routePrefix: 'decoder-stream-learned-windows', allowOptimization: false,
      request: (path, body) async {
        expect(path, '/decoder-stream-learned-windows/learned/batch');
        expect(body['reviewed'], {'id': 'learned'});
        return {'rows': 1, 'real_target_tokens': 1, 'sequence_lengths': [1], 'inputs': [[259]],
          'targets': [[258]], 'loss_mask': [[1]], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    expect(find.text('Check masked optimization'), findsNothing);
    expect(find.text('Saved optimizer checks'), findsNothing);
    await tester.tap(find.text('View arrays, masks and source references')); await tester.pumpAndSettle();
    expect(find.textContaining('259'), findsOneWidget);
  });

  testWidgets('learned optimizer confirmation and history stay on the learned route', (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: const {'id': 'learned'}, routePrefix: 'decoder-stream-learned-windows',
      request: (path, body) async {
        calls.add(path);
        if (path.endsWith('/optimization-checks')) return {'reports': <dynamic>[]};
        if (path.endsWith('/optimization-check')) {
          expect(body['reviewed_batch'], isNotNull); expect(body['confirmed'], true);
          return {'initial_batch_loss': 3.0, 'final_batch_loss': 2.0, 'vocabulary_size': 260, 'model_architecture_version': 2, 'evaluation': {}};
        }
        return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(calls.length, 1);
    await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm five-step optimizer check')); await tester.pumpAndSettle();
    expect(calls.last, '/decoder-stream-learned-windows/learned/optimization-check');
    expect(find.text('Learned vocabulary: 260 IDs · architecture version 2'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    await tester.tap(find.text('Saved optimizer checks')); await tester.pumpAndSettle();
    expect(calls.last, '/decoder-stream-learned-windows/learned/optimization-checks');
  });

  testWidgets('character version2 inputs keep review and numerical scope visible', (tester) async {
    final review = {'id': 'character', 'format': 'almg-stream-learned-windows-v2', 'schema_version': 2, 'fit_kind': 'character_bpe'};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: review, routePrefix: 'decoder-stream-learned-windows', request: (path, body) async {
        expect(body['reviewed'], review);
        if (path.endsWith('/optimization-check')) {
          expect(body['reviewed_batch']['schema_version'], 2);
          return {'format': 'almg-stream-learned-masked-optimizer-check-v2', 'schema_version': 2,
            'tokenizer_kind': 'character_bpe', 'vocabulary_size': 64, 'model_architecture_version': 1,
            'initial_batch_loss': 4.0, 'final_batch_loss': 3.0, 'evaluation': {}};
        }
        expect(path, '/decoder-stream-learned-windows/character/batch');
        return {'schema_version': 2, 'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm five-step optimizer check')); await tester.pumpAndSettle();
    expect(find.text('Learned vocabulary: 64 IDs · architecture version 1'), findsOneWidget);
    expect(find.text('Full-split character-BPE numerical check · no saved model or training approval'), findsOneWidget);
  });

  testWidgets('Unigram version3 review reaches its distinct numerical report', (tester) async {
    final review = {'id': 'unigram', 'format': 'almg-stream-learned-windows-v3', 'schema_version': 3, 'fit_kind': 'unigram'};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: review, routePrefix: 'decoder-stream-learned-windows', request: (path, body) async {
        expect(body['reviewed'], review);
        if (path.endsWith('/optimization-check')) {
          expect(body['reviewed_batch']['schema_version'], 3);
          return {'schema_version': 3, 'tokenizer_kind': 'unigram', 'vocabulary_size': 64, 'model_architecture_version': 1,
            'initial_batch_loss': 4.0, 'final_batch_loss': 3.0, 'evaluation': {}};
        }
        expect(path, '/decoder-stream-learned-windows/unigram/batch');
        return {'schema_version': 3, 'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle(); await tester.tap(find.text('Check masked optimization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm five-step optimizer check')); await tester.pumpAndSettle();
    expect(find.text('Full-split Unigram numerical check · no saved model or training approval'), findsOneWidget);
  });

  testWidgets('stream persistence saves fresh weights only after separate consent', (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: const {'id': 'stream'}, routePrefix: 'decoder-stream-learned-windows', allowPersistence: true,
      request: (path, body) async {
        calls.add(path);
        if (path.endsWith('/persistence-check')) {
          expect(body['confirmed'], true); expect(body['reviewed_batch'], isNotNull);
          return {'vocabulary_size': 64, 'tokenization_version': 3, 'architecture_version': 1, 'cpu_logit_max_error': 0};
        }
        return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check model/tokenizer persistence')); await tester.pumpAndSettle();
    expect(find.textContaining('Saved weights are untrained'), findsOneWidget);
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(calls.length, 1);
    await tester.tap(find.text('Check model/tokenizer persistence')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm private persistence check')); await tester.pumpAndSettle();
    expect(calls.last, '/decoder-stream-learned-windows/stream/persistence-check');
    expect(find.text('Stream model/tokenizer persistence verified'), findsOneWidget);
  });

  testWidgets('blocked streamed feasibility offers no training approval', (tester) async {
    var starts = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: const {'id': 'stream'}, routePrefix: 'decoder-stream-learned-windows', allowPersistence: true,
      request: (path, body) async {
        if (path.endsWith('/training-review')) return {'binding': 'reviewed'};
        if (path.endsWith('/training-feasibility')) return {'feasible': false, 'estimates': <String, dynamic>{}, 'blockers': ['Not enough trial memory']};
        if (path.endsWith('/training-begin')) starts++;
        return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2]};
      }))));
    await tester.pumpAndSettle(); await tester.ensureVisible(find.text('Approve manual streamed trial'));
    await tester.tap(find.text('Approve manual streamed trial')); await tester.pumpAndSettle();
    expect(find.text('Not enough trial memory'), findsOneWidget);
    expect(find.text('Approve twenty-step trial'), findsNothing); expect(starts, 0);
  });

  testWidgets('manual streamed trial requires approval and advances only on continuation', (tester) async {
    var starts = 0;
    var steps = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamModelBatchesDialog(
      reviewed: const {'id': 'stream'}, routePrefix: 'decoder-stream-learned-windows', allowPersistence: true,
      request: (path, body) async {
        if (path.endsWith('/training-review')) return {'binding': 'reviewed'};
        if (path.endsWith('/training-feasibility')) {
          return {'feasible': true, 'estimates': <String, dynamic>{}, 'blockers': <String>[],
            'duration_estimate': {'estimated_twenty_update_request_work_seconds': 6.0},
            'calibration': {'compatible_chunk_count': 1, 'observed_metal_peak_bytes': 200, 'observed_process_peak_rss_bytes': 500}};
        }
        if (path.endsWith('/hardware-profile')) {
          expect(body['confirmed'], true);
          return {'available': true, 'record': {'device': 'Fixture GPU'}};
        }
        if (path.endsWith('/measurements')) {
          expect(body['confirmed'], true);
          return {'records': [{'completed_steps': 5}], 'estimated_remaining_update_checkpoint_seconds': 3.0, 'remaining_chunks': 3,
            'duration_estimate': {'estimated_remaining_request_work_seconds': 4.0}};
        }
        if (path.endsWith('/training-begin')) {
          starts++;
          expect(body['reviewed'], {'binding': 'reviewed'});
          expect(body['confirmed'], true);
          expect(body['reviewed_feasibility']['feasible'], true);
          return {'id': 'trial', 'revision': 'zero', 'completed_steps': 0, 'status': 'paused'};
        }
        if (path.endsWith('/step')) {
          steps++;
          expect(body['expected_revision'], 'zero');
          if (steps == 1) throw StateError('Insufficient trial memory; previous checkpoint retained');
          return {'id': 'trial', 'revision': 'five', 'completed_steps': 5, 'status': 'paused'};
        }
        return {'rows': 1, 'real_target_tokens': 2, 'sequence_lengths': [2]};
      }))));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Approve manual streamed trial'));
    await tester.tap(find.text('Approve manual streamed trial')); await tester.pumpAndSettle();
    expect(find.textContaining('Measured calibration: 1 compatible training chunks'), findsOneWidget);
    expect(find.text('Estimated twenty-update request work including final evaluation: 6.00 seconds.'), findsOneWidget);
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(starts, 0);
    await tester.tap(find.text('Approve manual streamed trial')); await tester.pumpAndSettle();
    await tester.tap(find.text('Approve twenty-step trial')); await tester.pumpAndSettle();
    expect(starts, 1); expect(steps, 0);
    await tester.tap(find.text('View saved hardware profile')); await tester.pumpAndSettle();
    expect(find.text('Saved streamed-trial hardware profile'), findsOneWidget);
    expect(find.textContaining('Fixture GPU'), findsOneWidget);
    await tester.tap(find.text('Close').last); await tester.pumpAndSettle();
    await tester.tap(find.text('Run next five updates')); await tester.pumpAndSettle();
    expect(steps, 1); expect(find.textContaining('Insufficient trial memory'), findsOneWidget);
    expect(find.text('Saved progress: 0 / 20 updates · paused'), findsOneWidget);
    await tester.tap(find.text('Run next five updates')); await tester.pumpAndSettle();
    expect(steps, 2); expect(find.text('Saved progress: 5 / 20 updates · paused'), findsOneWidget);
    await tester.tap(find.text('View continuation measurements')); await tester.pumpAndSettle();
    expect(find.text('Saved measured chunks: 1'), findsOneWidget);
    expect(find.text('Estimated remaining update/checkpoint work: 3.0 seconds · 3 chunks.'), findsOneWidget);
    expect(find.text('Estimated remaining request work including final evaluation: 4.00 seconds.'), findsOneWidget);
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
