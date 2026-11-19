import 'dart:convert';
import 'dart:typed_data';
import 'package:file_selector/file_selector.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/streamed_source_client.dart';

void main() {
  test('uploads bounded chunks and resumes at the acknowledged offset', () async {
    final bytes = List<int>.generate(150000, (i) => i % 251);
    final file = XFile.fromData(Uint8List.fromList(bytes), name: 'source.txt');
    final stored = <int>[];
    var sealed = false;
    Map<String, dynamic> record = {'id': 'fixture', 'received_bytes': 0, 'total_bytes': bytes.length};
    Future<Map<String, dynamic>> request(String path, Map<String, dynamic> body) async {
      if (path.endsWith('/seal')) { sealed = true; return {...record, 'status': 'stored_not_prepared'}; }
      final chunk = base64Decode(body['data'] as String);
      expect(chunk.length, lessThanOrEqualTo(65536));
      expect(body['offset'], stored.length);
      expect(body['confirmed'], isTrue);
      stored.addAll(chunk);
      record = {...record, 'received_bytes': stored.length};
      return record;
    }
    var pause = false;
    final pending = await sendStreamedSource(file, record, request,
      onProgress: (_) => pause = true, shouldPause: () => pause);
    expect(pending['received_bytes'], 65536);
    expect(sealed, isFalse);
    final result = await sendStreamedSource(file, pending, request);
    expect(stored, bytes);
    expect(sealed, isTrue);
    expect(result['status'], 'stored_not_prepared');
  });
}
