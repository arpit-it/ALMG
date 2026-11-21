"""Read-only budget geometry for existing reviewed cyclic corpus recipes."""
from pathlib import Path
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
    from run_manifest import digest, file_digest


def exposure(windows, config, parameter_count, *, restore_step=0, reference_comparison=True):
    """Count real targets separately from dense padded model positions."""
    if type(restore_step) is not int or not 0 <= restore_step <= config['steps']:
        raise ValueError('Use an actual restored update counter within the original budget.')
    targets = 0
    for step in range(restore_step, config['steps']):
        _, arrays = training.batch_arrays(windows, step, config['batch_size'])
        targets += int(arrays[2].sum())
    updates = config['steps'] - restore_step
    draws = updates * config['batch_size']
    positions = draws * config['sequence_length']
    return {
        'optimizer_updates': updates, 'original_optimizer_updates': config['steps'],
        'restore_step': restore_step, 'effective_batch_rows': config['batch_size'],
        'initial_window_offset': restore_step * config['batch_size'] % len(windows),
        'final_window_offset': config['steps'] * config['batch_size'] % len(windows),
        'gradient_accumulation_steps': config['gradient_accumulation_steps'],
        'training_window_count': len(windows), 'training_window_draws': draws,
        'complete_window_passes': draws // len(windows),
        'remaining_window_draws': draws % len(windows),
        'stored_training_target_tokens': sum(sum(row['target_mask']) for row in windows),
        'recorded_training_target_tokens': targets, 'dense_training_token_positions': positions,
        'padding_target_positions': positions - targets, 'parameter_count': parameter_count,
        'training_tokens_per_parameter': targets / parameter_count,
        'comparison_reference_target_tokens': targets if reference_comparison else 0,
        'full_workflow_optimizer_target_tokens': targets * (2 if reference_comparison else 1),
        'measured': False,
        'scope': 'Calculated cyclic-window target exposure beginning at restore_step. Complete passes count full cyclic repetitions from that cursor; offsets retain the original schedule. Reference targets are included only when that trajectory will execute. Counts exclude CPU evaluation, causal checks and generation.',
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


def review_continuation(root, identifier):
    """Plan only the remaining original midpoint continuation; never approve it."""
    parent = training.read(root, identifier)
    config = parent['review']['config']
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Continuation budget planning currently requires reviewed cyclic settings versions five through nine.')
    resources = isolated.review_continuation(root, identifier)
    if resources['source']['record_revision'] != parent['revision']:
        raise ValueError('Saved corpus source changed during continuation budget planning.')
    origin = parent['review']['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    saved = training.inputs.read(root, resources['corpus_id'])
    _, current, _, windows, _ = training._source(root, initialized, saved)
    estimates = resources['estimates']
    result = {
        'format': 'almg-corpus-continuation-budget-review-v1', 'schema_version': 1,
        'execution_scope': 'original_midpoint_continuation',
        'source': resources['source'], 'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
        'config': config, 'restore_step': resources['restore_step'],
        'exposure': exposure(windows['train'], config, current['actual_parameter_count'],
                             restore_step=resources['restore_step'], reference_comparison=False),
        'resource_review': resources, 'feasible': resources['feasible'], 'blockers': resources['blockers'],
        'required_available_memory_bytes': estimates['required_available_memory_bytes'],
        'required_free_disk_bytes': estimates['required_free_disk_bytes'],
        'durable_checkpoint_disk_reserve_bytes': estimates['interruption_checkpoint_extra_disk_bytes'],
        'workflow_duration_estimate': estimates.get('corpus_continuation_work_estimate'),
        'optimizer_only_tokens_per_second': None, 'estimated_energy_wh': None, 'quality_token_requirement': None,
        'training_approved': False, 'release_approved': False,
        'limitations': 'Calculated remaining cyclic optimizer-target exposure starts at the validated restored counter and ends at the original approved budget. Completed work and the saved reference are not counted as new updates. Existing resource reserves remain conservative. Duration uses only exact compatible continuation trials and includes restore, lineage, evaluation and inference overhead; it is not an optimizer-only throughput or a wall-time guarantee. Energy and quality-token requirements remain unmeasured. Planning does not approve continuation; use its current resource review and separate explicit confirmation.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result
