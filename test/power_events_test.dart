import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/main.dart';

void main() {
  test('native power event includes desktop authorization and exact body length', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final received = server.first.then((request) async {
      expect(request.uri.path, '/runtime/power-event');
      expect(request.headers.value('X-Model-Studio'), 'desktop');
      final body = await request.cast<List<int>>().transform(utf8.decoder).join();
      expect(request.contentLength, utf8.encode(body).length);
      expect(jsonDecode(body), {'event': 'wake'});
      request.response.statusCode = 200;
      request.response.write('{}');
      await request.response.close();
    });
    try {
      await forwardPowerEvent('wake', port: server.port);
      await received;
    } finally {
      await server.close(force: true);
    }
  });
}
