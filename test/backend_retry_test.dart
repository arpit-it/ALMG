import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/chat.dart';

void main() {
  test('retries an unavailable backend and stops when connected', () async {
    var attempts = 0;
    await retryBackendConnection(
      refresh: () async {
        attempts++;
      },
      shouldRetry: () => attempts < 3,
      retryInterval: Duration.zero,
    );
    expect(attempts, 3);
  });

  test('does not retry once the retry window is exhausted', () async {
    var attempts = 0;
    await retryBackendConnection(
      refresh: () async {
        attempts++;
      },
      shouldRetry: () => true,
      retryWindow: Duration.zero,
    );
    expect(attempts, 1);
  });
}
