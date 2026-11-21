"""Read-only budget geometry for existing reviewed cyclic corpus recipes."""
from pathlib import Path
import math
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


def workflow_target_rate(exposure, work):
    """Derive a workflow rate from compatible measured durations, never kernel timing."""
    if not isinstance(work, dict) or work.get('measured') is not False:
        return None
    targets = exposure.get('full_workflow_optimizer_target_tokens')
    samples = work.get('source_records')
    if type(targets) is not int or targets <= 0 or not isinstance(samples, list) or not samples:
        return None
    try:
        times = [sample['elapsed_seconds'] for sample in samples]
        estimate = work['estimated_seconds']
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in [estimate, *times]):
            return None
        if estimate < max(times):
            return None
        rates = [targets / value for value in times]
        estimated_rate = targets / estimate
        if not all(math.isfinite(value) and value > 0 for value in [estimated_rate, *rates]):
            return None
        sources = [{'record_id': sample['record_id'], 'record_revision': sample['record_revision'],
                    'elapsed_seconds': elapsed, 'workflow_optimizer_targets_per_second': rate}
                   for sample, elapsed, rate in zip(samples, times, rates)]
    except (KeyError, TypeError, OverflowError):
        return None
    return {
        'format': 'almg-corpus-workflow-target-rate-estimate-v1', 'schema_version': 1,
        'measured': False, 'basis': 'exact_compatible_completed_workflow_observations',
        'full_workflow_optimizer_target_tokens': targets, 'sample_count': len(sources),
        'estimated_workflow_optimizer_targets_per_second': estimated_rate,
        'observed_min_workflow_optimizer_targets_per_second': min(rates),
        'observed_max_workflow_optimizer_targets_per_second': max(rates),
        'source_records': sources,
        'duration_limitations': work.get('limitations'),
        'limitations': 'Calculated masked optimizer-target counts divided by measured complete-worker durations, including reference work only when newly executed and including restore/admission/checkpoint/evaluation/inference overhead. Not direct optimizer-only throughput, unique corpus tokens, a confidence interval or a future speed guarantee. Observed range covers only the exact compatible completed samples; the estimate uses the existing duration headroom. No compatible positive timing or no remaining targets means no rate estimate.',
    }


def _finish(result):
    result['workflow_optimizer_target_rate_estimate'] = workflow_target_rate(result['exposure'], result['workflow_duration_estimate'])
    result['revision'] = digest({k: v for k, v in result.items() if k != 'revision'})
    return result


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
    return _finish(result)


def smaller_budgets(config):
    """Keep the recipe controls while considering only existing budgets up to the request."""
    for steps in (10, 20, 40, 80):
        if steps > config['steps']:
            continue
        if config['sequence_length'] == 16 or config['batch_size'] == 4:
            if steps > 20:
                continue
            version = 8 if config['sequence_length'] == 16 else 9
        else:
            version = 7 if steps == 80 else 6 if steps == 40 else 5
        yield training.configuration({**config, 'schema_version': version, 'steps': steps}, config['sequence_length'])


def review_quick_trial(root, initialized, reviewed_inputs, settings):
    """Propose an independently approved minimum-budget validation/calibration run."""
    if not isinstance(reviewed_inputs, dict) or not isinstance(reviewed_inputs.get('review'), dict):
        raise ValueError('Reopen saved reviewed corpus inputs before quick-trial planning.')
    config = training.configuration(settings, reviewed_inputs['review'].get('sequence_length'))
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Quick-trial planning supports reviewed cyclic settings versions five through nine.')
    trial_config = next(smaller_budgets(config))
    trial = review(root, initialized, reviewed_inputs, trial_config)
    result = {
        'format': 'almg-corpus-quick-trial-review-v1', 'schema_version': 1,
        'source': trial['source'], 'corpus_id': trial['corpus_id'], 'corpus_revision': trial['corpus_revision'],
        'requested_config': config, 'trial_config': trial_config, 'trial_budget_review': trial,
        'trial_purpose': 'bounded_configuration_validation_and_exact_budget_timing_calibration',
        'compatible_trial_timing_available': trial['workflow_duration_estimate'] is not None,
        'feasible': trial['feasible'], 'blockers': trial['blockers'],
        'training_approved': False, 'release_approved': False,
        'limitations': 'Independent read-only proposal for the smallest existing supported fresh-run budget, retaining other recipe controls. The trial executes both reference and recorded-training trajectories and existing numerical/checkpoint/inference gates. It needs its own current resource review, trial settings and separate explicit confirmation; it does not inherit approval or duration/token guarantees from another proposal. Unknown timing remains unknown until measured. Completed trial observations calibrate only exact compatible trial settings, never an unexecuted larger budget or language quality. Reopen duration-limited planning after the trial; no automatic full training or release follows.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result


def assess_quick_trial(root, identifier, settings):
    """Explain verified bounded trial evidence without promoting it to a larger run."""
    trial = training.read(root, identifier)
    approved = trial.get('review', {})
    if (trial.get('status') != 'completed' or trial.get('completed_steps') != 10
            or approved.get('config', {}).get('steps') != 10
            or approved.get('reference_resume_from') is not None or approved.get('training_resume_from') is not None
            or approved.get('execution_mode') != 'fresh_process' or training.feedback.measurements(trial) is None):
        raise ValueError('Select a completed ten-update fresh-worker corpus trial with measured timing.')
    saved = training.inputs.read(root, approved['corpus_id'])
    config = training.configuration(settings, saved['review']['sequence_length'])
    if config['schema_version'] not in (5, 6, 7, 8, 9) or next(smaller_budgets(config)) != approved['config']:
        raise ValueError('Requested recipe controls do not match this bounded trial; review a separate quick trial.')
    origin = approved['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    requested = review(root, initialized, saved, config)
    result = {
        'format': 'almg-corpus-quick-trial-assessment-v1', 'schema_version': 1,
        'trial_source': {'record_id': trial['id'], 'record_revision': trial['revision']},
        'trial_config': approved['config'], 'requested_config': config,
        'trial_validation': {
            'training_loss_decreased': trial['final_losses']['train'] < trial['initial_losses']['train'],
            'initial_training_loss': trial['initial_losses']['train'], 'final_training_loss': trial['final_losses']['train'],
            'checkpoint_restored_steps': trial['checkpoint_restored_steps'],
            'checkpoint_parameter_max_error': trial['checkpoint_parameter_max_error'],
            'checkpoint_optimizer_max_error': trial['checkpoint_optimizer_max_error'],
            'cpu_metal_max_error': trial['cpu_metal_max_error'],
            'saved_cpu_generation_verified': True,
        },
        'requested_update_budget_covered_by_trial': config == approved['config'],
        'requested_budget_review': requested,
        'compatible_requested_budget_timing_available': requested['workflow_duration_estimate'] is not None,
        'requested_execution_scope': 'independent_fresh_run_from_original_initialization',
        'feasible': requested['feasible'], 'blockers': requested['blockers'],
        'training_approved': False, 'release_approved': False,
        'limitations': 'Read-only assessment of a verified ten-update fresh-worker trial, not evidence of language quality or a larger update budget. Numeric/checkpoint/generation checks describe only that saved trial. Requested-budget timing requires its own exact compatible completed observations. The requested resource review is current and requires separate explicit confirmation of its settings for an independent fresh run from the original initialization. Trial weights are not automatically promoted, continued or released; changing other recipe controls requires separate trial evidence.',
        'implementation_sha256': file_digest(Path(__file__)),
    }
    result['revision'] = digest(result)
    return result


def review_limit(root, initialized, reviewed_inputs, settings, max_workflow_target_tokens=None, max_recorded_training_target_tokens=None, max_estimated_workflow_seconds=None, minimum_duration_samples=1):
    """Select a fresh-run budget satisfying every supplied scoped target limit."""
    limits = {'full_workflow_optimizer_target_tokens': max_workflow_target_tokens,
              'recorded_training_target_tokens': max_recorded_training_target_tokens}
    if type(minimum_duration_samples) is not int or not 1 <= minimum_duration_samples <= 20:
        raise ValueError('Require one through twenty compatible duration samples from the existing bounded history.')
    if minimum_duration_samples > 1 and max_estimated_workflow_seconds is None:
        raise ValueError('A repeated-duration evidence requirement needs an estimated workflow-duration limit.')
    if all(value is None for value in limits.values()) and max_estimated_workflow_seconds is None:
        raise ValueError('Provide at least one target-token or estimated workflow-duration limit.')
    if max_estimated_workflow_seconds is not None and (type(max_estimated_workflow_seconds) not in (int, float) or not 0 < max_estimated_workflow_seconds <= 2**63 - 1 or not math.isfinite(max_estimated_workflow_seconds)):
        raise ValueError('Use a positive finite estimated workflow-duration limit in seconds.')
    for value in limits.values():
        if value is not None and (type(value) is not int or not 0 < value <= 2**63 - 1):
            raise ValueError('Use positive integer target-token limits within signed 64-bit range.')
    if not isinstance(reviewed_inputs, dict) or not isinstance(reviewed_inputs.get('review'), dict):
        raise ValueError('Reopen saved reviewed corpus inputs before limit planning.')
    config = training.configuration(settings, reviewed_inputs['review'].get('sequence_length'))
    if config['schema_version'] not in (5, 6, 7, 8, 9):
        raise ValueError('Target-limit planning supports reviewed cyclic settings versions five through nine.')
    _, current, _, windows, _ = training._source(root, initialized, reviewed_inputs)
    candidates = []; previews = {}
    for candidate in smaller_budgets(config):
        counts = exposure(windows['train'], candidate, current['actual_parameter_count'])
        token_fit = all(limit is None or counts[key] <= limit for key, limit in limits.items())
        seconds = None; checked = False; sample_count = 0
        if max_estimated_workflow_seconds is not None and token_fit:
            preview = review(root, initialized, reviewed_inputs, candidate)
            previews[candidate['steps']] = preview; checked = True
            if preview['workflow_optimizer_target_rate_estimate'] is not None:
                seconds = preview['workflow_duration_estimate']['estimated_seconds']
                sample_count = preview['workflow_optimizer_target_rate_estimate']['sample_count']
        duration_fit = max_estimated_workflow_seconds is None or (seconds is not None and seconds <= max_estimated_workflow_seconds and sample_count >= minimum_duration_samples)
        candidates.append({'config': candidate, **{key: counts[key] for key in limits},
                           'estimated_workflow_seconds': seconds, 'duration_evidence_checked': checked,
                           'compatible_duration_sample_count': sample_count,
                           'within_limit': token_fit and duration_fit})
    fitting = [candidate for candidate in candidates if candidate['within_limit']]
    if not fitting:
        minimum = candidates[0]
        raise ValueError(f"No supported update budget fits the supplied limits (minimum recorded training {minimum['recorded_training_target_tokens']}, workflow {minimum['full_workflow_optimizer_target_tokens']}); duration-capped planning also requires at least {minimum_duration_samples} compatible completed timing samples.")
    selected_config = fitting[-1]['config']
    selected = previews.get(selected_config['steps']) or review(root, initialized, reviewed_inputs, selected_config)
    if any(limit is not None and selected['exposure'][key] > limit for key, limit in limits.items()):
        raise ValueError('Corpus exposure changed during target-limit planning; reopen the saved inputs.')
    result = {
        'format': 'almg-corpus-target-limit-review-v1', 'schema_version': 1,
        'source': selected['source'], 'corpus_id': selected['corpus_id'], 'corpus_revision': selected['corpus_revision'],
        'requested_config': config, 'max_workflow_optimizer_target_tokens': max_workflow_target_tokens,
        'max_recorded_training_target_tokens': max_recorded_training_target_tokens,
        'max_estimated_workflow_seconds': max_estimated_workflow_seconds,
        'minimum_duration_samples': minimum_duration_samples,
        'duration_evidence_policy': 'Sample-count filter for duration-capped planning only, using existing exact-compatible completed observations in bounded history. Repeated trials do not establish a confidence interval, language quality or a future runtime guarantee; existing estimate headroom and limitations remain unchanged.',
        'considered_budgets': candidates, 'selected_config': selected['config'], 'selected_budget_review': selected,
        'feasible': selected['feasible'], 'blockers': selected['blockers'],
        'training_approved': False, 'release_approved': False,
        'limitations': 'Read-only fresh-run planning: recorded-training targets count one recorded trajectory; workflow targets include both newly executed reference and recorded-training trajectories. Padding/evaluation/inference are excluded. Every supplied limit must fit; an omitted limit is unconstrained. Duration caps require exact compatible completed timing evidence and compare existing headroom-adjusted estimates, not guaranteed wall time. Unknown timing cannot pass a duration cap. Selects the largest existing supported step budget no greater than requested; other recipe controls are retained. Limits become an existing fixed update budget, not a runtime deadline or early-stop policy. Training needs the selected settings, their current resource review and separate explicit confirmation. Changing settings or corpus requires renewed review; resource blockers remain blockers. No quality-token requirement is inferred.',
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
    return _finish(result)


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
    return _finish(result)


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
    return _finish(result)


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
    return _finish(result)
