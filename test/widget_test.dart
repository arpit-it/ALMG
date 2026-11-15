import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/main.dart';

/// Verifies navigation to Settings while the local model is unavailable.
void main() {
  testWidgets('requires setup on home and opens model settings', (
    tester,
  ) async {
    await tester.pumpWidget(const ModelStudio());
    expect(find.text('Local model setup is required'), findsOneWidget);
    expect(find.text('Message Qwen'), findsNothing);
    await tester.tap(find.byTooltip('Open Settings'));
    await tester.pump();
    expect(find.text('Local model'), findsOneWidget);
    expect(find.text('Backend runtime'), findsOneWidget);
    expect(find.text('Model files'), findsOneWidget);
    expect(find.text('Stop runtime'), findsNothing);
    expect(find.text('Local model setup is required'), findsNothing);
    await tester.tap(find.byTooltip('Back'));
    await tester.pump();
    expect(find.text('Local model setup is required'), findsOneWidget);
  });
}
