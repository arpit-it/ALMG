import 'dart:convert';
import 'package:file_selector/file_selector.dart';

const localTextTypes = [XTypeGroup(label: 'UTF-8 text or Markdown', extensions: ['txt', 'md', 'markdown'])];

/// Bounds each read and rejects size changes instead of silently truncating input.
Future<List<Map<String, String>>> readLocalTextDocuments(List<XFile> files) async {
  if (files.isEmpty || files.length > 16) throw const FormatException('Select 1 to 16 local text documents.');
  final documents = <Map<String, String>>[];
  var total = 0;
  for (final file in files) {
    final allowance = (128000 - total).clamp(0, 65536);
    final length = await file.length();
    if (length > allowance) {
      throw const FormatException('Each document must fit 64 KiB; the selection must fit 128000 bytes.');
    }
    final bytes = <int>[];
    await for (final chunk in file.openRead(0, length)) {
      if (bytes.length + chunk.length > allowance) {
        throw const FormatException('Each document must fit 64 KiB; the selection must fit 128000 bytes.');
      }
      bytes.addAll(chunk);
    }
    if (bytes.length != length || await file.length() != length) {
      throw const FormatException('A selected document changed size. Select the current files again.');
    }
    utf8.decode(bytes); // Strict decoding; preserve exact original bytes in the request.
    total += bytes.length;
    documents.add({'name': file.name, 'data': base64Encode(bytes)});
  }
  return documents;
}
