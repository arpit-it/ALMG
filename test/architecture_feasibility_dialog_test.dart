import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/architecture_feasibility_dialog.dart';

void main() {
  testWidgets('unsupported precision hides confirmation until a supported report is reviewed', (tester) async {
    final precisions = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ArchitectureFeasibilityDialog(initialized: const {'id': 'init', 'plan_id': 'plan'}, request: (path, body) async {
      precisions.add(body['precision'] as String);
      final supported = body['precision'] == 'float32';
      return {'feasible': supported, 'hardware': {'metal_device': {'device_name': 'Fixture Metal'}, 'mlx_version': 'fixture'},
        'calibration': {'compatible_reports': [{'id': 'prior'}], 'observed_metal_peak_bytes': 1024, 'observed_process_peak_rss_bytes': 2048},
        'estimates': <String, dynamic>{}, 'blockers': supported ? <String>[] : ['float32 only'], 'recommendation': null};
    }))));
    await tester.pumpAndSettle(); expect(find.text('Confirm planned-model backward check'), findsOneWidget);
    expect(find.textContaining('Calibrated with 1 compatible isolated diagnostic report(s)'), findsOneWidget);
    await tester.tap(find.text('float32')); await tester.pumpAndSettle(); await tester.tap(find.text('float16').last); await tester.pumpAndSettle();
    expect(find.text('Confirm planned-model backward check'), findsNothing); expect(find.text('float32 only'), findsOneWidget);
    expect(precisions, ['float32', 'float16']);
  });
}
