import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/chat_export.dart';

void main() {
  test('export preserves message formatting, order, Unicode and attachment names', () {
    final result = conversationMarkdown('Orchard notes', [
      {'role': 'user', 'content': 'Check **pear** trees. 🌳', 'file_name': 'guide.pdf'},
      {'role': 'assistant', 'content': 'Water weekly.\n\n- See page 2.'},
    ]);
    expect(result, '# Orchard notes\n\n## You\n\nAttachment: guide\\.pdf\n\nCheck **pear** trees. 🌳\n\n## Qwen\n\nWater weekly.\n\n- See page 2.\n');
  });
  test('metadata cannot inject headings or links into export', () {
    final result = conversationMarkdown('Notes\n# Injected', [
      {'role': 'user', 'content': 'Original content', 'file_name': '[link](file)\n# title'},
    ]);
    expect(result, startsWith('# Notes \\# Injected\n'));
    expect(result, contains('Attachment: \\[link\\]\\(file\\) \\# title'));
    expect(result.split('\n## You').length, 2);
  });
}
