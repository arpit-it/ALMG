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
      expect(jsonDecode(body), {'event': 'wake', 'event_id': 'framing-fixture'});
      request.response.statusCode = 200;
      request.response.write('{}');
      await request.response.close();
    });
    try {
      await forwardPowerEvent('wake', port: server.port, eventId: 'framing-fixture');
      await received;
    } finally {
      await server.close(force: true);
    }
  });
  test('transient server failure retries the same event ID', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final bodies = <Map<String, dynamic>>[];
    final received = () async {
      await for (final request in server) {
        bodies.add(jsonDecode(await request.cast<List<int>>().transform(utf8.decoder).join()) as Map<String, dynamic>);
        request.response.statusCode = bodies.length == 1 ? 503 : 200;
        request.response.write('{}');
        await request.response.close();
        if (bodies.length == 2) break;
      }
    }();
    try {
      await forwardPowerEvent('wake', port: server.port, retryDelay: Duration.zero);
      await received;
      expect(bodies, hasLength(2));
      expect(bodies[0], bodies[1]);
      expect(bodies[0]['event_id'], isNotEmpty);
    } finally {
      await server.close(force: true);
    }
  });

  test('permanent rejection is not retried', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    var requests = 0;
    final received = server.first.then((request) async {
      requests++;
      await request.drain<void>();
      request.response.statusCode = 400;
      await request.response.close();
    });
    try {
      await expectLater(forwardPowerEvent('sleep', port: server.port, retryDelay: Duration.zero), throwsFormatException);
      await received;
      expect(requests, 1);
    } finally {
      await server.close(force: true);
    }
  });

}
