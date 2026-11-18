import 'dart:convert';

/// Formats extracted by the native PDF/OCR bridge on macOS.
const imageAttachmentExtensions = {'png', 'jpg', 'jpeg', 'heic', 'heif', 'tif', 'tiff', 'webp'};
const visualAttachmentExtensions = {'pdf', ...imageAttachmentExtensions};

/// Identifies OCR input so users can distinguish recognition from PDF text.
bool isImageAttachment(String name) => imageAttachmentExtensions.contains(name.split('.').last.toLowerCase());

/// Describes the content actually available to the text-only chat context.
String attachmentPreviewTitle(String name) => isImageAttachment(name)
    ? 'Recognized image text available to Qwen' : 'Text available to Qwen';

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
