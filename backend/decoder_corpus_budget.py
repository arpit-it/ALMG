"""Read-only budget geometry for existing reviewed cyclic corpus recipes."""
from pathlib import Path
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
    from run_manifest import digest, file_digest


def exposure(windows, config, parameter_count):
    """Count real targets separately from dense padded model positions."""
    targets = 0
    for step in range(config['steps']):
        _, arrays = training.batch_arrays(windows, step, config['batch_size'])
        targets += int(arrays[2].sum())
    draws = config['steps'] * config['batch_size']
    positions = draws * config['sequence_length']
    return {
        'optimizer_updates': config['steps'], 'effective_batch_rows': config['batch_size'],
        'gradient_accumulation_steps': config['gradient_accumulation_steps'],
        'training_window_count': len(windows), 'training_window_draws': draws,
        'complete_window_passes': draws // len(windows),
        'remaining_window_draws': draws % len(windows),
        'stored_training_target_tokens': sum(sum(row['target_mask']) for row in windows),
        'recorded_training_target_tokens': targets, 'dense_training_token_positions': positions,
        'padding_target_positions': positions - targets, 'parameter_count': parameter_count,
        'training_tokens_per_parameter': targets / parameter_count,
        'comparison_reference_target_tokens': targets,
        'full_workflow_optimizer_target_tokens': targets * 2,
        'measured': False,
        'scope': 'Calculated cyclic-window target exposure for one recorded trajectory; full fresh verification also executes the same reference trajectory. Counts exclude CPU evaluation, causal checks and generation.',
    }


def review(root, initialized, reviewed_inputs, settings):
    if not isinstance(reviewed_inputs, dict) or not isinstance(reviewed_inputs.get('review'), dict):
        raise ValueError('Reopen saved reviewed corpus inputs before budget planning.')
    config = training.configuration(settings, reviewed_inputs['review'].get('sequence_length'))
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Budget planning currently supports reviewed cyclic corpus settings versions five through nine.')
    resources = isolated.review(root, initialized, reviewed_inputs, config)
    saved, current, _, windows, _ = training._source(root, initialized, reviewed_inputs)
    estimates = resources['estimates']
    work = estimates.get('corpus_work_estimate')
    result = {
        'format': 'almg-corpus-budget-review-v1', 'schema_version': 1,
        'source': resources['source'], 'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
        'config': config, 'exposure': exposure(windows['train'], config, current['actual_parameter_count']),
        'resource_review': resources, 'feasible': resources['feasible'], 'blockers': resources['blockers'],
        'required_available_memory_bytes': estimates['required_available_memory_bytes'],
        'required_free_disk_bytes': estimates['required_free_disk_bytes'],
        'durable_checkpoint_disk_reserve_bytes': estimates['interruption_checkpoint_extra_disk_bytes'],
        'workflow_duration_estimate': work, 'optimizer_only_tokens_per_second': None,
        'estimated_energy_wh': None, 'quality_token_requirement': None,
        'training_approved': False, 'release_approved': False,
        'limitations': 'Token exposure is calculated from saved masks and approved cyclic window draws, not a language-quality token requirement. Memory/disk values are existing conservative admission reserves. Duration is unavailable without exact compatible completed trials; calibrated duration includes worker, reference, checkpoint/evaluation and inference overhead. No theoretical throughput or energy value is presented as measured. This read-only proposal does not queue or approve training; use a current resource review and separate explicit training confirmation.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result
