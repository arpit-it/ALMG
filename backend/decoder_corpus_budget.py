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
    return _continuation_report(root, parent, resources)


def _continuation_report(root, parent, resources):
    config = parent['review']['config']
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


def review_partial(root, identifier):
    """Plan new work from a validated canceled continuation, retaining its lineage."""
    partial = isolated._continuations().read(root, identifier)
    parent = training.read(root, partial['review']['source']['record_id'])
    if parent['review']['config']['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Partial-continuation budget planning requires reviewed cyclic settings versions five through nine.')
    resources = isolated.review_partial(root, identifier)
    if resources['resume_from']['record_revision'] != partial['revision']:
        raise ValueError('Retained continuation changed during budget planning.')
    result = _continuation_report(root, parent, resources)
    result.update(format='almg-corpus-partial-resume-budget-review-v1',
                  execution_scope='retained_canceled_continuation', resume_from=resources['resume_from'])
    result['revision'] = digest({k: v for k, v in result.items() if k != 'revision'})
    return result


def review_training_resume(root, identifier):
    """Count retained recorded-training work without repeating its saved reference."""
    parent = training.read(root, identifier)
    config = parent['review']['config']
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Recorded-training budget planning requires reviewed cyclic settings versions five through nine.')
    resources = isolated.review_training_resume(root, identifier)
    binding = resources['training_resume_from']
    if binding['record_revision'] != parent['revision']:
        raise ValueError('Retained training source changed during budget planning.')
    origin = parent['review']['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    saved = training.inputs.read(root, resources['corpus_id'])
    _, current, _, windows, _ = training._source(root, initialized, saved)
    estimates = resources['estimates']
    result = {
        'format': 'almg-corpus-training-resume-budget-review-v1', 'schema_version': 1,
        'execution_scope': 'retained_recorded_training',
        'source': resources['source'], 'training_resume_from': binding,
        'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
        'config': config, 'restore_step': binding['completed_steps'],
        'exposure': exposure(windows['train'], config, current['actual_parameter_count'],
                             restore_step=binding['completed_steps'], reference_comparison=False),
        'resource_review': resources, 'feasible': resources['feasible'], 'blockers': resources['blockers'],
        'required_available_memory_bytes': estimates['required_available_memory_bytes'],
        'required_free_disk_bytes': estimates['required_free_disk_bytes'],
        'durable_checkpoint_disk_reserve_bytes': estimates['interruption_checkpoint_extra_disk_bytes'],
        'workflow_duration_estimate': estimates.get('phase_resume_work_estimate'),
        'optimizer_only_tokens_per_second': None, 'estimated_energy_wh': None, 'quality_token_requirement': None,
        'training_approved': False, 'release_approved': False,
        'limitations': 'Calculated remaining cyclic recorded-training targets begin at the validated retained counter and end at the original budget. The completed reference is reused without new reference updates. Resource reserves remain conservative. Duration requires exact compatible completed training-phase resumes, includes worker/restore/lineage/evaluation/inference overhead and is not an optimizer-only throughput or a wall-time guarantee. Reference-phase recovery, energy and quality-token requirements are outside this report. Planning is read-only; resuming requires its current resource review and separate explicit confirmation.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result


def reference_recovery_exposure(windows, config, parameter_count, restore_step):
    """The reference resumes its cursor; recorded training still starts at zero."""
    recorded = exposure(windows, config, parameter_count, reference_comparison=False)
    reference = exposure(windows, config, parameter_count, restore_step=restore_step, reference_comparison=False)
    return {
        **recorded,
        'reference_restore_step': restore_step,
        'reference_optimizer_updates': reference['optimizer_updates'],
        'reference_initial_window_offset': reference['initial_window_offset'],
        'reference_final_window_offset': reference['final_window_offset'],
        'comparison_reference_target_tokens': reference['recorded_training_target_tokens'],
        'comparison_reference_dense_token_positions': reference['dense_training_token_positions'],
        'comparison_reference_padding_target_positions': reference['padding_target_positions'],
        'full_workflow_optimizer_updates': recorded['optimizer_updates'] + reference['optimizer_updates'],
        'full_workflow_optimizer_target_tokens': recorded['recorded_training_target_tokens'] + reference['recorded_training_target_tokens'],
        'full_workflow_dense_token_positions': recorded['dense_training_token_positions'] + reference['dense_training_token_positions'],
        'scope': 'Calculated new work only: remaining cyclic reference verification begins at reference_restore_step; the full recorded-training trajectory begins at restore_step zero. Training tokens per parameter describe only recorded training. Carried reference updates and evaluation/inference targets are excluded.',
    }


def review_reference_resume(root, identifier):
    """Plan remaining reference verification plus full original recorded training."""
    parent = training.read(root, identifier)
    config = parent['review']['config']
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Reference-recovery budget planning requires reviewed cyclic settings versions five through nine.')
    resources = isolated.review_reference_resume(root, identifier)
    binding = resources['reference_resume_from']
    if binding['record_revision'] != parent['revision']:
        raise ValueError('Retained reference source changed during budget planning.')
    origin = parent['review']['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    saved = training.inputs.read(root, resources['corpus_id'])
    _, current, _, windows, _ = training._source(root, initialized, saved)
    estimates = resources['estimates']
    result = {
        'format': 'almg-corpus-reference-resume-budget-review-v1', 'schema_version': 1,
        'execution_scope': 'retained_reference_then_original_recorded_training',
        'source': resources['source'], 'reference_resume_from': binding,
        'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
        'config': config, 'reference_restore_step': binding['completed_steps'],
        'exposure': reference_recovery_exposure(windows['train'], config, current['actual_parameter_count'], binding['completed_steps']),
        'resource_review': resources, 'feasible': resources['feasible'], 'blockers': resources['blockers'],
        'required_available_memory_bytes': estimates['required_available_memory_bytes'],
        'required_free_disk_bytes': estimates['required_free_disk_bytes'],
        'durable_checkpoint_disk_reserve_bytes': estimates['interruption_checkpoint_extra_disk_bytes'],
        'workflow_duration_estimate': estimates.get('phase_resume_work_estimate'),
        'optimizer_only_tokens_per_second': None, 'estimated_energy_wh': None, 'quality_token_requirement': None,
        'training_approved': False, 'release_approved': False,
        'limitations': 'Calculated new cyclic reference targets start at the retained reference counter; recorded training still executes its complete original budget from initialization. Carried reference work is excluded. Resource reserves remain conservative. Duration uses exact compatible completed reference-phase recoveries and includes worker/restore/lineage/checkpoint/evaluation/inference overhead, not optimizer-only throughput or a wall-time guarantee. Energy and quality-token requirements remain unmeasured. This read-only report does not approve recovery; use its current resource review and separate explicit confirmation.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result
