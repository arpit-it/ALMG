import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/decoder_architecture_plan_dialog.dart';

void main() {
  testWidgets('compact corpus recipe submits its exact layout and clears saved approval', (tester) async {
    Map<String,dynamic>? submitted;
    final review={'config':<String,dynamic>{},'calculated_parameter_count':14400,'estimates':{'weight_bytes':57600,'training_layout_bytes':460800}};
    await tester.pumpWidget(MaterialApp(home:Scaffold(body:DecoderArchitecturePlanDialog(request:(path,body) async {
      submitted=body;if(path.endsWith('/save'))return {'id':'a123456789','review':review};return review;
    }))));
    await tester.tap(find.text('Review architecture estimate'));await tester.pumpAndSettle();
    await tester.tap(find.text('Save reviewed architecture plan'));await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Tiny single-layer'));await tester.tap(find.text('Tiny single-layer'));await tester.pumpAndSettle();
    await tester.tap(find.text('Corpus three-layer / three-head').last);await tester.pumpAndSettle();
    expect(find.text('Initialize fresh planned model'),findsNothing);
    expect(find.textContaining('14,400 parameters across three layers'),findsOneWidget);
    await tester.tap(find.text('Review architecture estimate'));await tester.pumpAndSettle();
    final c=submitted!['config'] as Map;
    expect(c['layers'],3);expect(c['hidden_size'],24);expect(c['attention_heads'],3);expect(c['head_dim'],8);expect(c['feed_forward_size'],48);expect(c['context_length'],16);expect(c['vocab_size'],4);expect(c['batch_size'],4);expect(c['seed'],7);
  });

  testWidgets('backward diagnostic needs separate confirmation and discards updated weights', (tester) async {
    var checks = 0;
    final review = {'config': <String, dynamic>{}, 'calculated_parameter_count': 1664, 'estimates': {'weight_bytes': 6656, 'training_layout_bytes': 59392}};
    final saved = {'id': 'a123456789', 'review': review};
    final initialized = {'id': 'initialized', 'plan_id': saved['id'], 'actual_parameter_count': 1664, 'actual_weight_bytes': 6656, 'forward_shape': [2, 8, 64], 'causal_prefix_max_error': 0, 'reload_cpu_max_error': 0};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DecoderArchitecturePlanDialog(request: (path, body) async {
      if (path.endsWith('/review')) return review;
      if (path.endsWith('/save')) return saved;
      if (path.endsWith('/initialize')) return initialized;
      if (path.endsWith('/feasibility')) {
        return {'feasible': true, 'hardware': {'metal_device': {'device_name': 'Fixture Metal'}, 'mlx_version': 'fixture'},
          'estimates': <String, dynamic>{}, 'blockers': <dynamic>[], 'recommendation': null};
      }
      checks++; expect(body['confirmed'], true); expect(body['reviewed'], initialized);
      return {'initial_loss': 4.0, 'final_loss': 3.0, 'changed_parameter_tensors': ['head'], 'parameter_tensors': 1,
        'diagnostic_measurements': {'elapsed_seconds': 2.5, 'sampled_incremental_metal_bytes': 160, 'observed_increment_exceeds_estimate': true, 'conservative_observed_gpu_budget_bytes': 200,
          'isolated_trial_peak_measured': true, 'isolated_metal_peak_bytes': 200, 'isolated_process_peak_rss_bytes': 500, 'observed_peak_exceeds_estimate': true},
        'cpu_metal_max_error_before': 0, 'cpu_metal_max_error_after': 0, 'padding_check_applicable': true};
    }))));
    await tester.pumpAndSettle(); await tester.tap(find.text('Review architecture estimate')); await tester.pumpAndSettle();
    await tester.tap(find.text('Save reviewed architecture plan')); await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Initialize fresh planned model')); await tester.tap(find.text('Initialize fresh planned model')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm fresh architecture initialization')); await tester.pumpAndSettle();
    await tester.tap(find.text('Check planned-model backward pass')); await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(checks, 0);
    await tester.tap(find.text('Check planned-model backward pass')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm planned-model backward check')); await tester.pumpAndSettle();
    expect(checks, 1); expect(find.text('Planned-model backward diagnostic'), findsOneWidget);
    expect(find.textContaining('Measured diagnostic time: 2.5 seconds'), findsOneWidget);
    expect(find.textContaining('sampled increment exceeded the estimate'), findsOneWidget);
    expect(find.textContaining('Isolated diagnostic Metal peak: 200 bytes'), findsOneWidget);
    expect(find.textContaining('measured Metal peak exceeded the estimate'), findsOneWidget);
    expect(find.textContaining('Updated diagnostic weights were discarded'), findsOneWidget);
  });

  testWidgets('fresh planned model requires separate confirmation and reports forward-only scope', (tester) async {
    var initializations = 0;
    final review = {'config': <String, dynamic>{}, 'calculated_parameter_count': 8704, 'estimates': {'weight_bytes': 34816, 'training_layout_bytes': 466944}};
    final saved = {'id': 'a123456789', 'review': review};
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DecoderArchitecturePlanDialog(request: (path, body) async {
      if (path.endsWith('/review')) return review;
      if (path.endsWith('/save')) return saved;
      initializations++; expect(body['confirmed'], true); expect(body['reviewed'], saved);
      return {'actual_parameter_count': 8704, 'actual_weight_bytes': 34816, 'forward_shape': [2, 8, 128], 'causal_prefix_max_error': 0, 'reload_cpu_max_error': 0};
    }))));
    await tester.pumpAndSettle(); await tester.tap(find.text('Review architecture estimate')); await tester.pumpAndSettle();
    await tester.tap(find.text('Save reviewed architecture plan')); await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Initialize fresh planned model')); await tester.tap(find.text('Initialize fresh planned model')); await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel')); await tester.pumpAndSettle(); expect(initializations, 0);
    await tester.tap(find.text('Initialize fresh planned model')); await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm fresh architecture initialization')); await tester.pumpAndSettle();
    expect(initializations, 1); expect(find.text('Initialized architecture CPU check'), findsOneWidget);
    expect(find.textContaining('backward results are separate diagnostics'), findsOneWidget);
  });

  testWidgets('architecture review is read-only and editing invalidates save approval', (tester) async {
    var saves = 0;
    Map<String, dynamic>? review;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DecoderArchitecturePlanDialog(request: (path, body) async {
      if (path.endsWith('/review')) {
        review = {'config': body['config'], 'calculated_parameter_count': 1664, 'estimates': {'weight_bytes': 6656, 'training_layout_bytes': 59392}};
        return review!;
      }
      saves++; expect(body['confirmed'], true); expect(body['reviewed'], review);
      return {'id': 'a123456789', 'review': review};
    }))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review architecture estimate')); await tester.pumpAndSettle(); expect(saves, 0);
    expect(find.text('Calculated parameters: 1664'), findsOneWidget);
    await tester.tap(find.text('Save reviewed architecture plan')); await tester.pumpAndSettle(); expect(saves, 1);
    await tester.enterText(find.widgetWithText(TextField, 'Hidden width'), '16'); await tester.pumpAndSettle();
    expect(find.text('Save reviewed architecture plan'), findsNothing);
  });
}
