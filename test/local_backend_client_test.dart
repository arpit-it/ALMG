import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/local_backend_client.dart';

void main() {
  test('preview JSON uses explicit UTF-8 length and desktop authorization on the actual wire', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = LocalBackendClient(port: server.port);
    addTearDown(() async { client.close(); await server.close(force: true); });
    final body = {'confirmed': true, 'prompt': 'é', 'max_new_tokens': 12};
    final inbound = server.first;
    final pending = client.request('/decoder-imports/fixture/preview', body);
    final request = await inbound;
    expect(request.method, 'POST');
    expect(request.uri.path, '/decoder-imports/fixture/preview');
    expect(request.headers.value('X-Model-Studio'), 'desktop');
    expect(request.contentLength, utf8.encode(jsonEncode(body)).length);
    expect(request.headers.value(HttpHeaders.transferEncodingHeader), isNull);
    expect(jsonDecode(await request.cast<List<int>>().transform(utf8.decoder).join()), body);
    request.response.headers.contentType = ContentType.json;
    request.response.write(jsonEncode({'completion': 'a a'}));
    await request.response.close();
    expect(await pending, {'completion': 'a a'});
  });
}
