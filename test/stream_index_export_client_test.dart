import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/stream_index_export_client.dart';

void main() {
  late Directory root;
  late Map<String, dynamic> review;
  late Map<String, List<int>> files;
  setUp(() async {
    root = await Directory.systemTemp.createTemp('almg-export-test-');
    files = {'manifest.json': utf8.encode('{"private":"fixture"}'), 'records.sqlite3': List<int>.generate(150000, (i) => i % 251)};
    review = {'index_id': 'a' * 32, 'revision': 'b' * 64, 'files': {
      for (final entry in files.entries) entry.key: {'bytes': entry.value.length, 'sha256': entry.key == 'manifest.json' ? 'c' * 64 : 'd' * 64},
    }};
  });
  tearDown(() async { if (await root.exists()) await root.delete(recursive: true); });

  Future<Map<String, dynamic>> request(String path, Map<String, dynamic> body) async {
    expect(body['confirmed'], isTrue);
    if (path.endsWith('/export-seal')) return {'revision': review['revision'], 'export_manifest': review};
    final name = body['file_name'] as String; final offset = body['offset'] as int;
    final bytes = files[name]!; final end = offset + 65536 < bytes.length ? offset + 65536 : bytes.length;
    final chunk = bytes.sublist(offset, end);
    expect(body['limit'], 65536);
    return {'file_name': name, 'offset': offset, 'total_bytes': bytes.length, 'bytes': chunk.length, 'data': base64Encode(chunk)};
  }

  Future<String> hashFile(String path) async {
    final name = path.split(Platform.pathSeparator).last;
    expect(await File(path).readAsBytes(), files[name]);
    return (review['files'] as Map)[name]['sha256'] as String;
  }

  test('bounded export publishes only exact verified files and approved receipt', () async {
    final existing = File('${root.path}/user.txt'); await existing.writeAsString('preserve');
    final result = await saveStreamIndexExport(review, root, request, hashFile);
    expect(await File('${result.path}/records.sqlite3').readAsBytes(), files['records.sqlite3']);
    expect(jsonDecode(await File('${result.path}/export-manifest.json').readAsString()), review);
    expect(await existing.readAsString(), 'preserve');
    expect((await root.list().toList()).where((entry) => entry.path.contains('.almg-index-export-')), isEmpty);
  });

  test('cancel and checksum failure clean only owned staging output', () async {
    await expectLater(saveStreamIndexExport(review, root, request, hashFile, shouldCancel: () => true), throwsA(isA<StreamIndexExportCancelled>()));
    expect(await root.list().toList(), isEmpty);
    await expectLater(saveStreamIndexExport(review, root, request, (_) async => 'wrong'), throwsFormatException);
    expect(await root.list().toList(), isEmpty);
  });
}
