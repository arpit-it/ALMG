import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/attachment_preview.dart';

void main() {
  test('preview preserves PDF page markers and matches code-point limit', () {
    const text = 'Page 1\nOrchard\nPage 2\nWater weekly';
    expect(boundedAttachmentText(text), text);
    final long = List.filled(12001, '🌳').join();
    expect(boundedAttachmentText(long).runes.length, 12000);
    expect(boundedAttachmentText(long).endsWith('🌳'), isTrue);
  });
  test('text previews reject binary and invalid UTF-8', () {
    expect(readableAttachmentText(utf8.encode('Local notes')), 'Local notes');
    expect(readableAttachmentText([65, 0, 66]), isEmpty);
    expect(readableAttachmentText([255]), isEmpty);
  });
}
