import 'package:flutter/material.dart';

class DecoderCorpusLossTrace extends StatelessWidget {
  const DecoderCorpusLossTrace({super.key, required this.record});
  final Map<String, dynamic> record;

  @override
  Widget build(BuildContext context) {
    final logs = record['step_log'] as List? ?? const [];
    final rows = logs.whereType<Map>().where((entry) {
      final value = entry['batch_loss_before_update'];
      return value is num && value.isFinite && value >= 0;
    }).toList();
    if (rows.isEmpty) return const SizedBox.shrink();
    final reference = record['cancellation_phase'] == 'reference_verification';
    return ExpansionTile(
      title: Text(reference ? 'Per-update reference loss' : 'Per-update training loss'),
      subtitle: Text('Saved losses for ${rows.length} of ${logs.length} updates'),
      children: [
        const Text('Token-weighted current-batch loss before each optimizer update, without loss scaling. Batches can differ; held-out split losses are reported separately. Older entries without saved losses are left blank.'),
        for (final entry in rows)
          Text('Update ${entry['step']} · loss ${(entry['batch_loss_before_update'] as num).toStringAsFixed(6)} · ${entry['target_tokens']} target tokens'),
      ],
    );
  }
}
