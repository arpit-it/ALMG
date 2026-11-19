import 'dart:convert';
import 'package:file_selector/file_selector.dart';

typedef StreamSourceRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);

Future<Map<String, dynamic>> sendStreamedSource(XFile file, Map<String, dynamic> source,
    StreamSourceRequest request, {void Function(int)? onProgress, bool Function()? shouldPause}) async {
  var record = source;
  var offset = source['received_bytes'] as int;
  final total = source['total_bytes'] as int;
  if (await file.length() != total) throw const FormatException('The selected source size changed.');
  await for (final block in file.openRead(offset)) {
    for (var start = 0; start < block.length; start += 65536) {
      if (shouldPause?.call() == true) return record;
      final end = start + 65536 < block.length ? start + 65536 : block.length;
      final chunk = block.sublist(start, end);
      final next = await request('/decoder-streams/${source['id']}/chunk', {
        'confirmed': true, 'offset': offset, 'data': base64Encode(chunk),
      });
      if (next['id'] != source['id'] || next['received_bytes'] != offset + chunk.length) {
        throw const FormatException('The upload offset changed. Reopen the saved source to resume.');
      }
      record = next;
      offset += chunk.length;
      onProgress?.call(offset);
    }
  }
  if (shouldPause?.call() == true) return record;
  if (offset != total) throw const FormatException('The source ended before the expected byte count.');
  return request('/decoder-streams/${source['id']}/seal', {'confirmed': true});
}
