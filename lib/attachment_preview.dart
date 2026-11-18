import 'dart:convert';

/// Formats extracted by the native PDF/OCR bridge on macOS.
const visualAttachmentExtensions = {'pdf', 'png', 'jpg', 'jpeg', 'heic', 'tiff', 'webp'};

/// Matches the backend's 12,000 Unicode code-point context limit.
String boundedAttachmentText(String text) => String.fromCharCodes(text.runes.take(12000));

/// Returns readable UTF-8 text, excluding binary content with NUL bytes.
String readableAttachmentText(List<int> bytes) {
  try {
    final text = utf8.decode(bytes);
    return text.contains('\u0000') ? '' : boundedAttachmentText(text);
  } on FormatException {
    return '';
  }
}
