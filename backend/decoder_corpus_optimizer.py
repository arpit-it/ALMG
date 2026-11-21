"""Bounded FP32/mixed FP16 corpus training over saved, reviewed input snapshots."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid
import numpy as np
if __package__:
    from . import decoder_corpus_inputs as inputs, decoder_optimizer_fixture as optimizer
    from . import decoder_architecture_feasibility as hardware, decoder_architecture_backward as backward
    from . import decoder_optimizer_measurements as measurements, decoder_optimizer_estimates as estimates, decoder_mixed_precision as mixed, decoder_corpus_feedback as feedback, decoder_corpus_run_cancellations as run_cancellation
    from .planned_decoder import PlannedDecoder
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_inputs as inputs, decoder_optimizer_fixture as optimizer
    import decoder_architecture_feasibility as hardware, decoder_architecture_backward as backward
    import decoder_optimizer_measurements as measurements, decoder_optimizer_estimates as estimates, decoder_mixed_precision as mixed, decoder_corpus_feedback as feedback, decoder_corpus_run_cancellations as run_cancellation
    from planned_decoder import PlannedDecoder
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest


def configuration(settings, length):
    c = optimizer.configuration(settings)
    if c['schema_version'] not in (5,6) or c['sequence_length'] != length:
        raise ValueError('Corpus training currently requires version-5 or version-6 precision settings and the saved sequence length.')
    return c


def batch_arrays(windows, step, rows):
    indices = [(step * rows + offset) % len(windows) for offset in range(rows)]
    arrays = [np.array([windows[index][key] for index in indices], dtype=np.float32 if key == 'target_mask' else np.int32)
              for key in ('inputs', 'targets', 'target_mask')]
    return indices, arrays


def split_losses(model, windows):
    result = {}
    for part, rows in windows.items():
        total = count = 0
        for row in rows:
            mask = np.array([row['target_mask']], dtype=np.float32); targets = int(mask.sum())
            total += backward.cpu_loss(model, np.array([row['inputs']]), np.array([row['targets']]), mask) * targets
            count += targets
        result[part] = total / count
    return result


def train_updates(values, state, end, windows, c, model_config, mx, observer, stop=None):
    precision = c['compute_precision']; scale = c['loss_scale']
    _, _, gradient = mixed.functions(model_config, mx, scale) if precision == 'mixed_float16' else backward.metal_functions(model_config, mx)
    gradient_tolerance = 1e-3 if precision == 'mixed_float16' else 1e-5
    gradient_error = 0.0
    logs = []
    while state['step'] < end:
        if stop is not None and stop():
            break
        indices, arrays = batch_arrays(windows, state['step'], c['batch_size'])
        parameters = {name: mx.array(value) for name, value in values.items()}
        def gradients_for(batch):
            grads = gradient(parameters, *[mx.array(value) for value in batch]); mx.eval(grads)
            return mixed.unscale({name: np.array(value) for name, value in grads.items()}, scale)
        full = gradients_for(arrays)
        if c['gradient_accumulation_steps'] > 1:
            pieces = [(gradients_for([array[index:index + 1] for array in arrays]), int(arrays[2][index].sum()))
                      for index in range(c['batch_size'])]
            gradients = optimizer.accumulate(pieces)
            error = max(float(np.max(np.abs(full[name] - gradients[name]))) for name in full)
            gradient_error = max(gradient_error, error)
            if error > gradient_tolerance:
                raise ValueError('Token-weighted corpus accumulation differs from the full effective batch; checkpoints retained.')
        else:
            gradients = full
        values, state, entry = optimizer.update(values, gradients, state, c)
        entry.update(window_index=indices[0], window_indices=indices, target_tokens=int(arrays[2].sum()),
                     microbatches=c['gradient_accumulation_steps'])
        logs.append(entry); observer.sample(f"corpus_update_{state['step']}")
    return values, state, logs, gradient_error


def _source(root, initialized, reviewed_inputs):
    if not isinstance(reviewed_inputs, dict):
        raise ValueError('Reopen saved corpus inputs before reviewing training.')
    saved = inputs.read(root, reviewed_inputs.get('id'))
    if saved != reviewed_inputs:
        raise ValueError('Saved corpus input review changed.')
    source = saved['review']['source']
    _, current, model_bytes = hardware._source(root, source['plan_id'], initialized)
    if (source['initialization_id'] != current['id'] or source['initialization_revision'] != current['revision']
            or source['model_sha256'] != current['model_sha256']):
        raise ValueError('Corpus inputs belong to a different initialized model.')
    folder = Path(root) / 'decoder-corpus-inputs' / saved['id']
    windows = json.loads((folder / 'windows.json').read_text())
    tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text()))
    if current['config']['vocab_size'] != len(tokenizer.vocabulary) or current['actual_parameter_count'] > 16384:
        raise ValueError('Corpus tokenizer/model dimensions are incompatible.')
    length = saved['review']['sequence_length']
    if set(windows) != {'train', 'validation', 'test'} or length > current['config']['context_length']:
        raise ValueError('Invalid corpus split or context dimensions.')
    for part, rows in windows.items():
        if not 1 <= len(rows) <= (64 if part == 'train' else 32):
            raise ValueError('Corpus split window count exceeds bounded training limits.')
        for row in rows:
            if any(not isinstance(row.get(key), list) or len(row[key]) != length for key in ('inputs', 'targets', 'target_mask')):
                raise ValueError('Invalid corpus window dimensions.')
            if (any(type(value) is not int or not 0 <= value < current['config']['vocab_size'] for key in ('inputs', 'targets') for value in row[key])
                    or any(type(value) is not int or value not in (0, 1) for value in row['target_mask']) or not sum(row['target_mask'])):
                raise ValueError('Invalid token IDs or empty corpus target mask.')
    return saved, current, model_bytes, windows, tokenizer


def review(root, initialized, reviewed_inputs, settings, execution_mode='shared_backend'):
    if execution_mode not in ('shared_backend','fresh_process'):raise ValueError('Choose a supported corpus execution mode.')
    saved, current, model_bytes, windows, _ = _source(root, initialized, reviewed_inputs)
    c = configuration(settings, saved['review']['sequence_length'])
    profile = hardware.hardware(root)
    reserve = hardware.estimate(current['config'], model_bytes)
    corpus_bytes = sum((Path(root) / 'decoder-corpus-inputs' / saved['id'] / name).stat().st_size for name in saved['files'])
    moments = current['actual_weight_bytes'] * (2 if c['optimizer'] == 'adamw' else 0)
    reserve.update(optimizer_state_bytes=moments, dataset_storage_bytes=corpus_bytes,
                   dataset_storage_scope='immutable_reviewed_text_corpus_inputs',
                   required_available_memory_bytes=reserve['required_available_memory_bytes'] + moments * 4 + corpus_bytes * 8 + (current['actual_weight_bytes'] * 2 if c['gradient_accumulation_steps'] > 1 else 0),
                   required_free_disk_bytes=reserve['required_free_disk_bytes'] + max(2 * 1024 ** 2, current['actual_weight_bytes'] * 128),
                   assumptions='Conservative FP32 model/runtime reserves plus corpus snapshots and CPU optimizer moments; shared process observations are not isolated peaks.',
                   optimizer_updates=c['steps'], checkpoint_step=c['steps'] // 2,
                   compute_precision=c['compute_precision'], loss_scale=c['loss_scale'], master_parameter_dtype='float32',
                   precision_scope='Conservative FP32 reserves retained; mixed FP16 matrix products do not establish memory savings.',
                   effective_batch_rows=c['batch_size'], gradient_accumulation_steps=c['gradient_accumulation_steps'],
                   gradient_accumulation_buffer_bytes=current['actual_weight_bytes'] if c['gradient_accumulation_steps'] > 1 else 0)
    reserve['interruption_checkpoint_count']=2
    reserve['interruption_checkpoint_extra_disk_bytes']=2*max(2*1024**2,current['actual_weight_bytes']*256)
    reserve['required_free_disk_bytes']+=reserve['interruption_checkpoint_extra_disk_bytes']
    reserve['required_available_memory_bytes']+=current['actual_weight_bytes']*8
    reasons = list(profile['errors'])
    if len(windows['train']) > c['steps'] * c['batch_size']:
        reasons.append('Choose enough optimizer updates to visit every saved training window at least once.')
    if c['batch_size'] > current['config']['batch_size']:
        reasons.append('Selected corpus batch exceeds the initialized model planning batch.')
    if c['batch_size'] % c['gradient_accumulation_steps']:
        reasons.append('Two corpus microbatches require an effective batch of two rows.')
    if profile['system'] != 'Darwin' or profile['machine'] != 'arm64' or not profile['metal_available']:
        reasons.append('Corpus gradients require Apple silicon with MLX Metal.')
    if not hardware._fits(profile, reserve):
        reasons.append('Current memory/disk does not cover corpus optimizer reserves.')
    result = {'format': 'almg-corpus-optimizer-review-v4' if execution_mode=='fresh_process' else 'almg-corpus-optimizer-review-v3', 'schema_version': 4 if execution_mode=='fresh_process' else 3,
              'execution_mode':execution_mode,
              'source': saved['review']['source'], 'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
              'config': c, 'model_config': current['config'], 'runtime': estimates.runtime(profile),
              'splits': saved['review']['splits'], 'estimates': reserve, 'hardware': profile,
              'feasible': not reasons, 'blockers': reasons, 'training_approved': False, 'release_approved': False,
              'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                  ('decoder_corpus_optimizer.py', 'decoder_corpus_inputs.py', 'decoder_optimizer_fixture.py', 'decoder_corpus_feedback.py', 'decoder_corpus_isolated.py', 'decoder_corpus_worker.py', 'decoder_corpus_run_cancellations.py', 'decoder_corpus_reference_resume.py', 'decoder_corpus_training_resume.py', 'decoder_corpus_phase_feedback.py', 'decoder_corpus_interruptions.py',
                   'decoder_architecture_backward.py', 'decoder_mixed_precision.py', 'planned_decoder.py', 'decoder_tokenizer.py')})}
    reserve['calculated_memory_reserve_bytes']=reserve['required_available_memory_bytes']
    memory,work=feedback.feedback(history(root,initialized,reviewed_inputs),result) if execution_mode=='fresh_process' else (None,None)
    reserve['isolated_corpus_memory']=memory;reserve['corpus_work_estimate']=work
    if memory is not None:reserve['required_available_memory_bytes']=max(reserve['required_available_memory_bytes'],memory['calculated_memory_floor_bytes'])
    if not hardware._fits(profile,reserve) and not any('memory/disk' in reason for reason in reasons):reasons.append('Current memory/disk does not cover measured corpus worker calibration reserves.')
    result['feasible']=not reasons
    result['revision'] = digest(result)
    return result


def _folder(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Select a saved corpus optimizer run.')
    folder=Path(root)/'decoder-corpus-optimizer-runs'/identifier
    checkpoint=Path(root)/'decoder-corpus-interruption-checkpoints'/identifier
    return checkpoint if not folder.exists() and (checkpoint/'record.json').exists() else folder


def _generated(model, tokenizer):
    tokens = optimizer._generate(model)
    return tokens, tokenizer.decode_preview(tokens) if hasattr(tokenizer, 'decode_preview') else tokenizer.decode(tokens)


def run(root, confirmed, initialized, reviewed_inputs, settings, approved, execution_mode='shared_backend', request_id=None, reference_resume_id=None, training_resume_id=None):
    if confirmed is not True:
        raise ValueError('Explicitly confirm corpus training and private checkpoint/model storage.')
    if request_id is not None:run_cancellation.validate(request_id)
    if __package__:from . import decoder_corpus_reference_resume as reference_resume
    else:import decoder_corpus_reference_resume as reference_resume
    if __package__:from . import decoder_corpus_training_resume as training_resume
    else:import decoder_corpus_training_resume as training_resume
    if reference_resume_id is not None and training_resume_id is not None:raise ValueError('Choose one retained corpus phase.')
    parent = None if reference_resume_id is None else reference_resume.source(root, reference_resume_id)[0]
    current = review(root, initialized, reviewed_inputs, settings, execution_mode) if parent is None else reference_resume.review(root, reference_resume_id, execution_mode)
    if training_resume_id is not None:
        parent=training_resume.source(root,training_resume_id)[0]
        current=training_resume.review(root,training_resume_id,execution_mode)
    keys = ('format', 'schema_version', 'source', 'corpus_id', 'corpus_revision', 'config', 'model_config', 'runtime', 'splits', 'estimates', 'implementation_sha256', 'execution_mode', 'reference_resume_from', 'training_resume_from')
    if (not isinstance(approved, dict) or approved.get('revision') != digest({k: v for k, v in approved.items() if k != 'revision'})
            or any(approved.get(key) != current.get(key) for key in keys)):
        raise ValueError('Corpus optimizer review changed. Reopen it before training.')
    if not current['feasible'] or approved.get('feasible') is not True:
        raise ValueError('Corpus optimizer training is blocked by resources or window coverage.')
    saved, source, _, windows, tokenizer = _source(root, initialized, reviewed_inputs)
    c = current['config']; plan_id = source['plan_id']
    source_model = hardware.initializations._folder(root, plan_id) / source['id'] / 'model.json'
    import mlx.core as mx
    observer = measurements.OptimizerMeasurements(mx)
    model = PlannedDecoder.load(source_model)
    initial_parameters = {key: value.copy() for key, value in model.parameters.items()}
    identifier = uuid.uuid4().hex; folder = _folder(root, identifier); folder.mkdir(parents=True)
    def cpu_scores(values):
        model.parameters = values
        return split_losses(model, windows)
    initial_losses = cpu_scores(initial_parameters)
    reference=reference_state=None;reference_log=[];first=[];phase='reference_verification'
    reference_prefix=[] if parent is None else parent['reference_step_log']
    try:
        with mx.stream(mx.gpu):
            fp32_logits, fp32_loss, fp32_gradient = backward.metal_functions(model.config, mx)
            precision = c['compute_precision']; scale = c['loss_scale']
            logits, loss, gradient = mixed.functions(model.config, mx, scale) if precision == 'mixed_float16' else (fp32_logits, fp32_loss, fp32_gradient)
            gradient_tolerance = 1e-3 if precision == 'mixed_float16' else 1e-5
            _, first_batch = batch_arrays(windows['train'], 0, c['batch_size'])
            initial_master = {name: mx.array(value) for name, value in initial_parameters.items()}
            initial_compute_loss = float(loss(initial_master, *[mx.array(value) for value in first_batch]).item())
            initial_fp32_loss = float(fp32_loss(initial_master, *[mx.array(value) for value in first_batch]).item())
            altered = first_batch[0].copy(); cut = max(1, altered.shape[1] // 2)
            altered[:, cut:] = (altered[:, cut:] + 1) % model.config['vocab_size']
            causal_error = float(mx.max(mx.abs(logits(initial_master, mx.array(first_batch[0]))[:, :cut] - logits(initial_master, mx.array(altered))[:, :cut])).item())
            if not math.isfinite(initial_compute_loss) or abs(initial_compute_loss - initial_fp32_loss) > .05 or causal_error > 1e-5:
                raise ValueError('Corpus precision failed initial FP32 loss or causal-prefix checks; no completed run published.')
            gradient_error = 0.0
            def optimize(values, state, end):
                nonlocal gradient_error
                values, state, logs, error = train_updates(values, state, end, windows['train'], c, model.config, mx, observer,stop=lambda:run_cancellation.requested(root,approved,request_id))
                gradient_error = max(gradient_error, error)
                if state['step']<end:raise run_cancellation.Stopped(values,state,logs,phase)
                return values, state, logs
            empty = {'step': 0, 'm': {}, 'v': {}}; midpoint = c['steps'] // 2
            if training_resume_id is None:
                reference_values, reference_initial_state = (initial_parameters, empty) if parent is None else reference_resume.state(root,parent)
                reference, reference_state, reference_log = optimize(reference_values, reference_initial_state, c['steps'])
                reference_log = reference_prefix + reference_log
                phase='checkpointed_training'
                if parent is None and execution_mode=='fresh_process':
                    if __package__:from . import decoder_corpus_interruptions
                    else:import decoder_corpus_interruptions
                    decoder_corpus_interruptions.publish(root,folder,initialized,reviewed_inputs,approved,current,model,tokenizer,windows,initial_losses,initial_parameters,empty,reference,reference_state,reference_log,[],request_id)
                values,state,first=optimize(initial_parameters,empty,midpoint)
            else:
                reference,reference_state=training_resume.reference(root,parent)
                reference_log=parent['reference_step_log'];phase='checkpointed_training'
                values,state=reference_resume.state(root,parent);first=parent['step_log']
                if state['step']<midpoint:
                    values,state,new_logs=optimize(values,state,midpoint)
                    first=first+new_logs
            if state['step']==midpoint:
                model.parameters=values
                optimizer.checkpoint(folder/f'step-{midpoint}',model,state,c,approved['revision'])
                if parent is None and execution_mode=='fresh_process':
                    if __package__:from . import decoder_corpus_interruptions
                    else:import decoder_corpus_interruptions
                    decoder_corpus_interruptions.publish(root,folder,initialized,reviewed_inputs,approved,current,model,tokenizer,windows,initial_losses,values,state,reference,reference_state,reference_log,first,request_id)
                restored,state=optimizer.restore(folder/f'step-{midpoint}',c,approved['revision'])
                values=restored.parameters
            elif training_resume_id is not None:
                checkpoint_model,checkpoint_state=optimizer.restore(_folder(root,parent['id'])/f'step-{midpoint}',c,parent['review']['revision'])
                optimizer.checkpoint(folder/f'step-{midpoint}',checkpoint_model,checkpoint_state,c,approved['revision'])
            values, state, last = optimize(values, state, c['steps'])
            parameter_error = max(float(np.max(np.abs(values[name] - reference[name]))) for name in values)
            moment_error = max([0.] + [float(np.max(np.abs(state[kind][name] - reference_state[kind][name]))) for kind in ('m', 'v') for name in state[kind]])
            probe = windows['test'][0]['inputs']
            cpu = PlannedDecoder(model.config); cpu.parameters = values
            master = {name: mx.array(value) for name, value in values.items()}
            gpu_scores = fp32_logits(master, mx.array([probe]))
            compute_error = float(mx.max(mx.abs(gpu_scores - logits(master, mx.array([probe])))).item())
            cpu_error = float(np.max(np.abs(cpu.logits([probe]) - np.array(gpu_scores))))
    except run_cancellation.Stopped as event:
        if event.phase=='reference_verification':event.logs=reference_prefix+event.logs
        return run_cancellation.save(root,folder,identifier,initialized,reviewed_inputs,approved,current,model,tokenizer,windows,initial_losses,event,reference,reference_state,reference_log,first,observer,request_id)
    final_losses = cpu_scores(values)
    if (not all(math.isfinite(value) for value in [*initial_losses.values(), *final_losses.values()])
            or final_losses['train'] >= initial_losses['train'] or parameter_error > 1e-7 or moment_error > 1e-7 or cpu_error > 1e-5 or not math.isfinite(compute_error) or compute_error > .05):
        raise ValueError('Corpus training failed loss/checkpoint/CPU checks. Saved checkpoints are retained for inspection.')
    model.parameters = values; model.save(folder / 'trained-model.json')
    (folder / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
    loaded = PlannedDecoder.load(folder / 'trained-model.json')
    generated, text = _generated(loaded, tokenizer)
    if _generated(model, tokenizer) != (generated, text):
        raise ValueError('Saved corpus model generation changed after reload; artifacts retained.')
    _source(root, initialized, reviewed_inputs)
    observed = observer.finish()
    observed['scope'] = 'bounded_corpus_optimizer_in_shared_backend' if execution_mode=='shared_backend' else 'phase_samples_inside_isolated_corpus_worker'
    if execution_mode=='fresh_process':observed['limitations']='Synchronized phase samples inside one fresh corpus worker, not its isolated lifetime peaks. See isolated_workflow_measurements when published. Sampling starts after admission and excludes worker bootstrap/history validation; no total wall-time or future-duration guarantee.'
    observed['limitations'] += ' Corpus scope: starts after admission/snapshot validation and includes model loading, checkpoint restore, all split evaluations and tokenizer-backed CPU generation. Fresh runs execute both trajectories; reference resume executes only the retained reference remainder followed by the original recorded training budget. Recorded-training resume reuses the completed reference and executes only its remaining original training updates.'
    record = {'format': 'almg-corpus-optimizer-run-v3', 'schema_version': 3, 'id': identifier,
              'status':'completed','request_id':request_id,
              'created_at': datetime.now(timezone.utc).isoformat(), 'review': approved, 'admission': current,
              'initial_losses': initial_losses, 'final_losses': final_losses,
              'completed_steps': state['step'], 'scheduler_completed_steps': state['step'],
              'checkpoint_restored_steps': midpoint, 'checkpoint_parameter_max_error': parameter_error,
              'checkpoint_optimizer_max_error': moment_error, 'cpu_metal_max_error': cpu_error,
              'effective_batch_rows': c['batch_size'], 'gradient_accumulation_steps': c['gradient_accumulation_steps'],
              'full_batch_gradient_max_error': gradient_error, 'full_batch_gradient_tolerance': gradient_tolerance,
              'compute_precision': precision, 'loss_scale': scale, 'master_parameter_dtype': 'float32',
              'master_gradient_dtype': 'float32', 'optimizer_state_dtype': 'float32',
              'initial_compute_loss': initial_compute_loss, 'initial_fp32_reference_loss': initial_fp32_loss,
              'initial_precision_loss_difference': abs(initial_compute_loss - initial_fp32_loss),
              'causal_prefix_max_error': causal_error, 'compute_fp32_logits_max_error': compute_error,
              'split_loss_runtime': 'numpy_cpu_fp32_master_parameters_float64_reduction',
              'step_log': first + last, 'generated_token_ids': generated, 'generated_text': text,
              'inference_runtime': 'planned_decoder_numpy_cpu', 'pretrained_student_weights_loaded': False,
              'training_approved': True, 'release_approved': False, 'source_initialization_modified': False,
              'workflow_measurements': observed,
              'limitations': 'Small reviewed text corpus, FP32 or bounded mixed FP16 SGD/AdamW, FP32 masters, one/two effective rows and one/two token-weighted microbatches only. Held-out losses are diagnostics; no quality/release gate. Fresh runs execute both comparison trajectories. Reference resume carries saved updates and executes only the reference remainder before original checkpointed training. Saved midpoint continuation and retained reference resume require separate approval; recorded-training partial resume likewise requires its own exact-state approval. Fixed-scale mixed precision is validated only for bounded corpus fixtures; split losses use the saved FP32 master model, not a general quality or memory-savings claim.',
              'files': {str(path.relative_to(folder)): file_digest(path) for path in folder.rglob('*') if path.is_file()}}
    record.update(reference_resume.metadata(approved,c['steps']))
    record.update(training_resume.metadata(approved,state['step']))
    if parent is not None:record['reference_step_log']=reference_log
    record['revision'] = digest(record)
    (folder / 'record.json').write_text(json.dumps(record, allow_nan=False, indent=2))
    return read(root, identifier)


def read(root, identifier, _seen=None):
    folder = _folder(root, identifier)
    seen=set() if _seen is None else set(_seen)
    if identifier in seen or len(seen)>16:raise ValueError('Cyclic or excessive corpus reference ancestry.')
    seen.add(identifier)
    if (folder / 'record.json').stat().st_size > 256000:
        raise ValueError('Corpus optimizer record exceeds size limit.')
    record = json.loads((folder / 'record.json').read_text())
    if __package__:from . import decoder_corpus_reference_resume as reference_resume
    else:import decoder_corpus_reference_resume as reference_resume
    reference_resume.lineage(root,record,seen)
    if __package__:from . import decoder_corpus_training_resume
    else:import decoder_corpus_training_resume
    decoder_corpus_training_resume.lineage(root,record,seen)
    if record.get('format') in ('almg-corpus-optimizer-run-v4','almg-corpus-optimizer-run-v5','almg-corpus-optimizer-run-v6'):return run_cancellation.read(root,folder,record)
    approved = record['review']; c = configuration(approved['config'], approved['config']['sequence_length'])
    midpoint = c['steps'] // 2
    expected = {'trained-model.json', 'tokenizer.json', *[f'step-{midpoint}/{name}' for name in ('model.json', 'optimizer.json', 'checkpoint.json')]}
    if (record.get('status','completed')!='completed' or (record.get('format'), record.get('schema_version')) not in (('almg-corpus-optimizer-run-v1', 1), ('almg-corpus-optimizer-run-v2', 2), ('almg-corpus-optimizer-run-v3', 3)) or record.get('id') != identifier
            or record.get('revision') != digest({k: v for k, v in record.items() if k != 'revision'})
            or set(record.get('files', {})) != expected or any((folder / name).stat().st_size > 16 * 1024 ** 2 or file_digest(folder / name) != sha for name, sha in record['files'].items())
            or approved.get('revision') != digest({k: v for k, v in approved.items() if k != 'revision'})
            or record['completed_steps'] != c['steps'] or record['scheduler_completed_steps'] != c['steps']):
        raise ValueError('Corpus optimizer record or artifacts changed.')
    optimizer.restore(folder / f'step-{midpoint}', c, approved['revision'])
    tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text()))
    saved = inputs.read(root, approved['corpus_id'])
    if saved['revision'] != approved['corpus_revision'] or tokenizer.fingerprint() != saved['review']['tokenizer_sha256']:
        raise ValueError('Corpus/tokenizer lineage changed.')
    if record['schema_version'] < 3 and c['compute_precision'] != 'float32':
        raise ValueError('Legacy corpus runs require their original FP32 computation.')
    if record['schema_version'] == 3:
        checks = {'initial_precision_loss_difference': .05, 'causal_prefix_max_error': 1e-5, 'compute_fp32_logits_max_error': .05}
        if (record.get('compute_precision') != c['compute_precision'] or record.get('loss_scale') != c['loss_scale']
                or any(record.get(key) != 'float32' for key in ('master_parameter_dtype', 'master_gradient_dtype', 'optimizer_state_dtype'))
                or any(type(record.get(key)) not in (int, float) or not math.isfinite(record[key]) or not 0 <= record[key] <= bound for key, bound in checks.items())):
            raise ValueError('Invalid saved corpus precision checks.')
    if record['schema_version'] == 1:
        if c['batch_size'] != 1 or c['gradient_accumulation_steps'] != 1:
            raise ValueError('Legacy corpus runs require their original single-row configuration.')
    else:
        error = record.get('full_batch_gradient_max_error')
        tolerance = 1e-3 if c['compute_precision'] == 'mixed_float16' else 1e-5
        if (record.get('effective_batch_rows') != c['batch_size'] or record.get('gradient_accumulation_steps') != c['gradient_accumulation_steps']
                or c['batch_size'] % c['gradient_accumulation_steps'] or type(error) not in (float, int)
                or not math.isfinite(error) or not 0 <= error <= tolerance or record.get('full_batch_gradient_tolerance') != tolerance
                or len(record.get('step_log', [])) != c['steps']):
            raise ValueError('Invalid saved corpus accumulation state.')
        windows = json.loads((Path(root) / 'decoder-corpus-inputs' / saved['id'] / 'windows.json').read_text())['train']
        for step, entry in enumerate(record['step_log']):
            indices, arrays = batch_arrays(windows, step, c['batch_size'])
            if (entry.get('step') != step + 1 or entry.get('window_indices') != indices or entry.get('window_index') != indices[0]
                    or entry.get('target_tokens') != int(arrays[2].sum()) or entry.get('microbatches') != c['gradient_accumulation_steps']):
                raise ValueError('Saved corpus update window/counter binding changed.')
    model = PlannedDecoder.load(folder / 'trained-model.json')
    if model.config != approved['model_config'] or _generated(model, tokenizer) != (record['generated_token_ids'], record['generated_text']):
        raise ValueError('Saved corpus model inference changed.')
    if 'isolated_workflow_measurements' in record:
        if approved.get('execution_mode')!='fresh_process' or feedback.measurements(record) is None:raise ValueError('Corpus isolation measurements lack a matching execution policy.')
    return record


def history(root, initialized, reviewed_inputs):
    saved, _, _, _, _ = _source(root, initialized, reviewed_inputs)
    records = [read(root, path.parent.name) for path in (Path(root) / 'decoder-corpus-optimizer-runs').glob('*/record.json')]
    return sorted([record for record in records if record['review']['corpus_id'] == saved['id']], key=lambda item: item['created_at'])[-20:]
