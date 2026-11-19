import 'dart:convert';
import 'dart:io';

import 'backend_address.dart';

/// Desktop-authenticated JSON requests with explicit UTF-8 byte lengths.
class LocalBackendClient {
  LocalBackendClient({this.port = backendPort});

  final int port;
  final _client = HttpClient()..connectionTimeout = const Duration(seconds: 4);

  Future<Map<String, dynamic>> request(String path, [Map<String, dynamic>? body]) async {
    final uri = Uri.parse('http://127.0.0.1:$port$path');
    final request = body == null ? await _client.getUrl(uri) : await _client.postUrl(uri);
    request.headers.set('X-Model-Studio', 'desktop');
    if (body != null) {
      final bytes = utf8.encode(jsonEncode(body));
      request.headers.contentType = ContentType.json;
      request.contentLength = bytes.length;
      request.add(bytes);
    }
    final response = await request.close().timeout(const Duration(seconds: 8));
    final text = await response.transform(utf8.decoder).join().timeout(const Duration(seconds: 8));
    final data = Map<String, dynamic>.from(jsonDecode(text) as Map);
    if (response.statusCode >= 400) throw FormatException(data['error']?.toString() ?? 'Could not load local model.');
    return data;
  }

  void close() => _client.close(force: true);
}
