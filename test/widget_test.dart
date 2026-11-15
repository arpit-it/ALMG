import 'package:flutter/material.dart';
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
  testWidgets(
    'training shows both panes on desktop and tabs on narrow windows',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1100, 700));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(const MaterialApp(home: StudioPage()));
      expect(find.text('Training conversation'), findsOneWidget);
      expect(find.text('Model creation'), findsOneWidget);
      expect(find.text('Waiting for a model goal'), findsOneWidget);

      await tester.binding.setSurfaceSize(const Size(600, 700));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(Tab, 'Model creation'));
      await tester.pumpAndSettle();
      expect(find.text('Waiting for a model goal'), findsOneWidget);
    },
  );
}
