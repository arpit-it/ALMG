/// Escapes metadata while leaving message Markdown intact.
String _metadata(String value) => value.replaceAll(RegExp(r'\s+'), ' ').trim()
    .replaceAllMapped(RegExp(r'([\\`*_{}\[\]()#+.!|>~-])'), (match) => '\\${match[0]}');

/// Formats the saved transcript and attachment names for local Markdown export.
String conversationMarkdown(String title, List<dynamic> messages) {
  final document = StringBuffer('# ${_metadata(title)}\n');
  for (final message in messages) {
    final speaker = message['role'] == 'user' ? 'You' : 'Qwen';
    document.writeln('\n## $speaker\n');
    if (message['file_name'] case final String name when name.isNotEmpty) {
      document.writeln('Attachment: ${_metadata(name)}\n');
    }
    document.writeln(message['content']);
  }
  return document.toString();
}
