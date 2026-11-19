import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:file_selector/file_selector.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/local_text_documents.dart';

class MisreportedFile extends XFile {
  MisreportedFile() : super('unused', name: 'growing.md');
  int? requestedEnd;
  @override Future<int> length() async => 1;
  @override Stream<Uint8List> openRead([int? start, int? end]) async* {
    requestedEnd = end;
    yield Uint8List(65537);
  }
}
class SizeChangingFile extends XFile {
  SizeChangingFile() : super('unused', name: 'changed.md');
  int reads = 0;
  @override Future<int> length() async => ++reads == 1 ? 1 : 2;
  @override Stream<Uint8List> openRead([int? start, int? end]) async* {
    yield Uint8List.fromList([65]);
  }
}
void main() {
  test('preserves Markdown source bytes and filenames with strict UTF-8 decoding', () async {
    final root = await Directory.systemTemp.createTemp('almg-text-read-');
    addTearDown(() => root.delete(recursive: true));
    final bytes = utf8.encode('\ufeff# Café\r\n\n**Local** text.\n');
    final file = await File('${root.path}/source.md').writeAsBytes(bytes);
    final documents = await readLocalTextDocuments([XFile(file.path)]);
    expect(documents.single['name'], 'source.md');
    expect(base64Decode(documents.single['data']!), bytes);
    expect(() => readLocalTextDocuments([XFile.fromData(Uint8List.fromList([255]), name: 'bad.txt')]), throwsFormatException);
  });
  test('limits actual streamed bytes instead of trusting a stale size', () async {
    final file = MisreportedFile();
    await expectLater(readLocalTextDocuments([file]), throwsFormatException);
    expect(file.requestedEnd, 1);
    await expectLater(readLocalTextDocuments([SizeChangingFile()]), throwsFormatException);
    await expectLater(readLocalTextDocuments([
      XFile.fromData(Uint8List(64000), name: 'one.txt'),
      XFile.fromData(Uint8List(64001), name: 'two.md'),
    ]), throwsFormatException);
    await expectLater(readLocalTextDocuments(List.generate(17, (_) => XFile('unused'))), throwsFormatException);
  });
}
