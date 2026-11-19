import 'dart:convert';
import 'package:file_selector/file_selector.dart';

typedef StreamSourceRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);

Future<Map<String, dynamic>> sendStreamedSource(XFile file, Map<String, dynamic> source,
    StreamSourceRequest request, {void Function(int)? onProgress, bool Function()? shouldPause}) async {
  var record = source;
  var offset = source['received_bytes'] as int;
  final total = source['total_bytes'] as int;
  final advertised = source['upload_batch_chunks'] ?? 1;
  if (advertised is! int || advertised < 1 || advertised > 16) throw const FormatException('Unsupported upload batch limit.');
  if (await file.length() != total) throw const FormatException('The selected source size changed.');
  final pending = <String>[];
  var pendingBytes = 0;
  Future<void> flush() async {
    if (pending.isEmpty) return;
    final next = await request('/decoder-streams/${source['id']}/${advertised == 1 ? 'chunk' : 'chunks'}', {
      'confirmed': true, 'offset': offset,
      if (advertised == 1) 'data': pending.single else 'chunks': List<String>.from(pending),
    });
    if (next['id'] != source['id'] || next['received_bytes'] != offset + pendingBytes) {
      throw const FormatException('The upload offset changed. Reopen the saved source to resume.');
    }
    record = next; offset += pendingBytes; pending.clear(); pendingBytes = 0;
    onProgress?.call(offset);
  }
  await for (final block in file.openRead(offset)) {
    for (var start = 0; start < block.length; start += 65536) {
      if (shouldPause?.call() == true) return record;
      final end = start + 65536 < block.length ? start + 65536 : block.length;
      final chunk = block.sublist(start, end);
      pending.add(base64Encode(chunk)); pendingBytes += chunk.length;
      if (pending.length == advertised) await flush();
    }
  }
  if (shouldPause?.call() == true) return record;
  await flush();
  if (shouldPause?.call() == true) return record;
  if (offset != total) throw const FormatException('The source ended before the expected byte count.');
  return request('/decoder-streams/${source['id']}/seal', {'confirmed': true});
}
