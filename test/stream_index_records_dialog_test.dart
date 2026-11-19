import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_index_records_dialog.dart';

Map<String, dynamic> page(Map<String, dynamic> body) => {
  'records': [{'first_line': 7, 'split': body['split'] == 'all' ? 'train' : body['split'], 'occurrences': 2,
    'text_hygiene': {'score': 75}, 'text_excerpt': '[CONTACT_REDACTED] local excerpt', 'excerpt_truncated': false,
    'privacy_matches': 1, 'privacy_findings': [{'category': 'email_address'}], 'source_sha256': 'source-hash'}],
  'next_cursor': body['cursor'] == null ? {'revision': 'revision', 'after': 'group', 'split': body['split']} : null,
};

void main() {
  testWidgets('token-window rows show source offsets and token IDs', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(indexId: 'fixture',
      recordsPath: '/decoder-stream-windows/fixture/records', request: (path, body) async {
        expect(path, '/decoder-stream-windows/fixture/records');
        return {'records': [{'first_line': 8, 'split': 'train', 'token_offset': 16,
          'token_ids': [65, 66, 67], 'text_excerpt': 'Token IDs: [65, 66, 67]'}], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    expect(find.textContaining('token offset 16'), findsOneWidget);
    expect(find.text('Token IDs: [65, 66, 67]'), findsOneWidget);
    expect(find.textContaining('potential contact details'), findsNothing);
  });

  testWidgets('overlap findings show pair similarity without language or hygiene claims', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(
      indexId: 'fixture', recordsPath: '/decoder-stream-overlap/fixture/records', request: (path, body) async {
        expect(path, '/decoder-stream-overlap/fixture/records');
        return {'records': [{'first_line': 3, 'split': 'train', 'occurrences': 1,
          'similarity': 0.95, 'cross_split': true, 'records': [{'first_line': 3}, {'first_line': 7}],
          'text_excerpt': 'Original texts omitted.'}], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    expect(find.textContaining('overlap 0.95'), findsOneWidget);
    expect(find.textContaining('cross-split'), findsOneWidget);
    expect(find.textContaining('potential contact details'), findsNothing);
  });

  testWidgets('language records show estimates without invented hygiene or privacy scores', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(
      indexId: 'fixture', recordsPath: '/decoder-stream-languages/fixture/records', request: (path, body) async {
        expect(path, '/decoder-stream-languages/fixture/records');
        return {'records': [{'first_line': 3, 'split': 'train', 'occurrences': 1,
          'language': 'und', 'status': 'unknown', 'reason': 'provider_unavailable',
          'text_excerpt': 'Original text omitted.', 'source_sha256': 'source-hash'}], 'next_cursor': null};
      }))));
    await tester.pumpAndSettle();
    expect(find.textContaining('language und'), findsOneWidget);
    expect(find.textContaining('potential contact details'), findsNothing);
    expect(find.textContaining('hygiene'), findsNothing);
  });

  testWidgets('record review pages forward/back and resets its cursor when filtering', (tester) async {
    final calls = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(indexId: 'fixture', request: (path, body) async {
      expect(path, '/decoder-stream-indexes/fixture/records');
      expect(body['confirmed'], isTrue);
      calls.add(Map<String, dynamic>.from(body));
      return page(body);
    }))));
    await tester.pumpAndSettle();
    expect(find.text('[CONTACT_REDACTED] local excerpt'), findsOneWidget);
    await tester.tap(find.text('Next records')); await tester.pumpAndSettle();
    expect(calls.last['cursor'], isNotNull);
    await tester.tap(find.text('Previous records')); await tester.pumpAndSettle();
    expect(calls.last['cursor'], isNull);
    await tester.tap(find.byType(DropdownButton<String>)); await tester.pumpAndSettle();
    await tester.tap(find.text('validation').last); await tester.pumpAndSettle();
    expect(calls.last['split'], 'validation'); expect(calls.last['cursor'], isNull);
    await tester.ensureVisible(find.text('Source details and findings')); await tester.pumpAndSettle();
    await tester.tap(find.text('Source details and findings')); await tester.pumpAndSettle();
    expect(find.textContaining('source-hash'), findsOneWidget);
  });

  testWidgets('long review bounds back history and can reset to the first page', (tester) async {
    final calls = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(indexId: 'fixture', request: (path, body) async {
      calls.add(Map<String, dynamic>.from(body));
      return {...page(body), 'next_cursor': {'revision': 'revision', 'after': 'group${calls.length}', 'split': body['split']}};
    }))));
    await tester.pumpAndSettle();
    for (var i = 0; i < 60; i++) { await tester.tap(find.text('Next records')); await tester.pumpAndSettle(); }
    var previousPages = 0;
    while (tester.widget<TextButton>(find.ancestor(of: find.text('Previous records'), matching: find.byType(TextButton))).onPressed != null) {
      await tester.tap(find.text('Previous records')); await tester.pumpAndSettle(); previousPages++;
      if (previousPages > 60) break;
    }
    expect(previousPages, lessThanOrEqualTo(49));
    await tester.tap(find.text('First records')); await tester.pumpAndSettle();
    expect(calls.last['cursor'], isNull);
  });

  testWidgets('failed record page offers retry without requesting training', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StreamIndexRecordsDialog(indexId: 'fixture', request: (path, body) async {
      expect(path.endsWith('/records'), isTrue);
      if (attempts++ == 0) throw StateError('fixture unavailable');
      return page(body);
    }))));
    await tester.pumpAndSettle();
    expect(find.textContaining('fixture unavailable'), findsOneWidget);
    await tester.tap(find.text('Retry record page')); await tester.pumpAndSettle();
    expect(find.text('[CONTACT_REDACTED] local excerpt'), findsOneWidget);
    expect(attempts, 2);
  });
}
