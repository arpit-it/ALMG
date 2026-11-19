import 'dart:convert';
import 'dart:io';

typedef IndexExportRequest = Future<Map<String, dynamic>> Function(String, Map<String, dynamic>);
class StreamIndexExportCancelled implements Exception { const StreamIndexExportCancelled(); }

Future<Directory> saveStreamIndexExport(Map<String, dynamic> review, Directory parent, IndexExportRequest request,
    Future<String> Function(String) hashFile, {void Function(int, int)? onProgress, bool Function()? shouldCancel}) async {
  final id = review['index_id'] as String;
  final revision = review['revision'] as String;
  if (!RegExp(r'^[a-f0-9]{32}$').hasMatch(id) || !RegExp(r'^[a-f0-9]{64}$').hasMatch(revision)) {
    throw const FormatException('Invalid text-index export identity.');
  }
  final files = Map<String, dynamic>.from(review['files'] as Map);
  if (files.length != 2 || !files.containsKey('manifest.json') || !files.containsKey('records.sqlite3')) {
    throw const FormatException('Unsupported text-index export files.');
  }
  var total = 0;
  for (final entry in files.values) {
    final length = (entry as Map)['bytes'];
    if (length is! int || length < 1) throw const FormatException('Invalid reviewed export length.');
    total += length;
  }
  final staged = await parent.createTemp('.almg-index-export-');
  try {
    var completed = 0;
    for (final name in ['manifest.json', 'records.sqlite3']) {
      final metadata = files[name] as Map;
      final length = metadata['bytes'] as int;
      final path = '${staged.path}/$name';
      final output = await File(path).open(mode: FileMode.write);
      try {
        var offset = 0;
        while (offset < length) {
          if (shouldCancel?.call() == true) throw const StreamIndexExportCancelled();
          final block = await request('/decoder-stream-indexes/$id/export-chunk', {
            'confirmed': true, 'review': review, 'file_name': name, 'offset': offset, 'limit': 65536,
          });
          final bytes = base64Decode(block['data'] as String);
          if (block['file_name'] != name || block['offset'] != offset || block['total_bytes'] != length
              || block['bytes'] != bytes.length || bytes.isEmpty || bytes.length > 65536 || offset + bytes.length > length) {
            throw const FormatException('Text-index export chunk did not match the reviewed file.');
          }
          await output.writeFrom(bytes);
          offset += bytes.length; completed += bytes.length; onProgress?.call(completed, total);
        }
        await output.flush();
      } finally { await output.close(); }
      if (await hashFile(path) != metadata['sha256']) throw const FormatException('Saved text-index file hash mismatch.');
    }
    if (shouldCancel?.call() == true) throw const StreamIndexExportCancelled();
    final sealed = await request('/decoder-stream-indexes/$id/export-seal', {'confirmed': true, 'review': review});
    if (sealed['revision'] != revision) throw const FormatException('The export verification revision changed.');
    if (shouldCancel?.call() == true) throw const StreamIndexExportCancelled();
    await File('${staged.path}/export-manifest.json').writeAsString(const JsonEncoder.withIndent('  ').convert(review), flush: true);
    final destination = Directory('${parent.path}/stream-index-${id.substring(0, 8)}-${revision.substring(0, 8)}-${DateTime.now().microsecondsSinceEpoch}');
    if (await destination.exists()) throw const FileSystemException('The export destination already exists.');
    return await staged.rename(destination.path);
  } finally {
    if (await staged.exists()) await staged.delete(recursive: true);
  }
}
