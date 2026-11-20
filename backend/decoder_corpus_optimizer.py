"""Bounded FP32 corpus training over explicitly saved, reviewed input snapshots."""
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
    from . import decoder_optimizer_measurements as measurements, decoder_optimizer_estimates as estimates
    from .planned_decoder import PlannedDecoder
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_inputs as inputs, decoder_optimizer_fixture as optimizer
    import decoder_architecture_feasibility as hardware, decoder_architecture_backward as backward
    import decoder_optimizer_measurements as measurements, decoder_optimizer_estimates as estimates
    from planned_decoder import PlannedDecoder
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest


def configuration(settings, length):
    c = optimizer.configuration(settings)
    if c['schema_version'] != 5 or c['sequence_length'] != length or c['compute_precision'] != 'float32':
        raise ValueError('Corpus training currently requires version-5 FP32 settings and the saved sequence length.')
    return c


def batch_arrays(windows, step, rows):
    indices = [(step * rows + offset) % len(windows) for offset in range(rows)]
    arrays = [np.array([windows[index][key] for index in indices], dtype=np.float32 if key == 'target_mask' else np.int32)
              for key in ('inputs', 'targets', 'target_mask')]
    return indices, arrays


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


def review(root, initialized, reviewed_inputs, settings):
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
                   effective_batch_rows=c['batch_size'], gradient_accumulation_steps=c['gradient_accumulation_steps'],
                   gradient_accumulation_buffer_bytes=current['actual_weight_bytes'] if c['gradient_accumulation_steps'] > 1 else 0)
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
    result = {'format': 'almg-corpus-optimizer-review-v2', 'schema_version': 2,
              'source': saved['review']['source'], 'corpus_id': saved['id'], 'corpus_revision': saved['revision'],
              'config': c, 'model_config': current['config'], 'runtime': estimates.runtime(profile),
              'splits': saved['review']['splits'], 'estimates': reserve, 'hardware': profile,
              'feasible': not reasons, 'blockers': reasons, 'training_approved': False, 'release_approved': False,
              'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                  ('decoder_corpus_optimizer.py', 'decoder_corpus_inputs.py', 'decoder_optimizer_fixture.py',
                   'decoder_architecture_backward.py', 'planned_decoder.py', 'decoder_tokenizer.py')})}
    result['revision'] = digest(result)
    return result


def _folder(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Select a saved corpus optimizer run.')
    return Path(root) / 'decoder-corpus-optimizer-runs' / identifier


def _generated(model, tokenizer):
    tokens = optimizer._generate(model)
    return tokens, tokenizer.decode_preview(tokens) if hasattr(tokenizer, 'decode_preview') else tokenizer.decode(tokens)


def run(root, confirmed, initialized, reviewed_inputs, settings, approved):
    if confirmed is not True:
        raise ValueError('Explicitly confirm corpus training and private checkpoint/model storage.')
    current = review(root, initialized, reviewed_inputs, settings)
    keys = ('format', 'schema_version', 'source', 'corpus_id', 'corpus_revision', 'config', 'model_config', 'runtime', 'splits', 'estimates', 'implementation_sha256')
    if (not isinstance(approved, dict) or approved.get('revision') != digest({k: v for k, v in approved.items() if k != 'revision'})
            or any(approved.get(key) != current[key] for key in keys)):
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
        result = {}
        for part, rows in windows.items():
            total = count = 0
            for row in rows:
                mask = np.array([row['target_mask']], dtype=np.float32); targets = int(mask.sum())
                total += backward.cpu_loss(model, np.array([row['inputs']]), np.array([row['targets']]), mask) * targets
                count += targets
            result[part] = total / count
        return result
    initial_losses = cpu_scores(initial_parameters)
    with mx.stream(mx.gpu):
        logits, loss, gradient = backward.metal_functions(model.config, mx)
        gradient_error = 0.0
        def optimize(values, state, end):
            nonlocal gradient_error
            logs = []
            while state['step'] < end:
                indices, arrays = batch_arrays(windows['train'], state['step'], c['batch_size'])
                parameters = {name: mx.array(value) for name, value in values.items()}
                def gradients_for(batch):
                    grads = gradient(parameters, *[mx.array(value) for value in batch]); mx.eval(grads)
                    return {name: np.array(value) for name, value in grads.items()}
                full = gradients_for(arrays)
                if c['gradient_accumulation_steps'] > 1:
                    pieces = [(gradients_for([array[index:index + 1] for array in arrays]), int(arrays[2][index].sum()))
                              for index in range(c['batch_size'])]
                    gradients = optimizer.accumulate(pieces)
                    error = max(float(np.max(np.abs(full[name] - gradients[name]))) for name in full)
                    gradient_error = max(gradient_error, error)
                    if error > 1e-5:
                        raise ValueError('Token-weighted corpus accumulation differs from the full effective batch; checkpoints retained.')
                else:
                    gradients = full
                values, state, entry = optimizer.update(values, gradients, state, c)
                entry.update(window_index=indices[0], window_indices=indices, target_tokens=int(arrays[2].sum()),
                             microbatches=c['gradient_accumulation_steps'])
                logs.append(entry); observer.sample(f"corpus_update_{state['step']}")
            return values, state, logs
        empty = {'step': 0, 'm': {}, 'v': {}}; midpoint = c['steps'] // 2
        reference, reference_state, _ = optimize(initial_parameters, empty, c['steps'])
        halfway, state, first = optimize(initial_parameters, empty, midpoint)
        model.parameters = halfway
        optimizer.checkpoint(folder / f'step-{midpoint}', model, state, c, approved['revision'])
        restored, state = optimizer.restore(folder / f'step-{midpoint}', c, approved['revision'])
        values, state, last = optimize(restored.parameters, state, c['steps'])
        parameter_error = max(float(np.max(np.abs(values[name] - reference[name]))) for name in values)
        moment_error = max([0.] + [float(np.max(np.abs(state[kind][name] - reference_state[kind][name]))) for kind in ('m', 'v') for name in state[kind]])
        probe = windows['test'][0]['inputs']
        cpu = PlannedDecoder(model.config); cpu.parameters = values
        gpu_scores = logits({name: mx.array(value) for name, value in values.items()}, mx.array([probe]))
        cpu_error = float(np.max(np.abs(cpu.logits([probe]) - np.array(gpu_scores))))
    final_losses = cpu_scores(values)
    if (not all(math.isfinite(value) for value in [*initial_losses.values(), *final_losses.values()])
            or final_losses['train'] >= initial_losses['train'] or parameter_error > 1e-7 or moment_error > 1e-7 or cpu_error > 1e-5):
        raise ValueError('Corpus training failed loss/checkpoint/CPU checks. Saved checkpoints are retained for inspection.')
    model.parameters = values; model.save(folder / 'trained-model.json')
    (folder / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
    loaded = PlannedDecoder.load(folder / 'trained-model.json')
    generated, text = _generated(loaded, tokenizer)
    if _generated(model, tokenizer) != (generated, text):
        raise ValueError('Saved corpus model generation changed after reload; artifacts retained.')
    _source(root, initialized, reviewed_inputs)
    observed = observer.finish()
    observed['scope'] = 'bounded_corpus_optimizer_in_shared_backend'
    observed['limitations'] += ' Corpus scope: starts after admission/snapshot validation and includes model loading, both training trajectories, checkpoint restore, all split evaluations and tokenizer-backed CPU generation.'
    record = {'format': 'almg-corpus-optimizer-run-v2', 'schema_version': 2, 'id': identifier,
              'created_at': datetime.now(timezone.utc).isoformat(), 'review': approved, 'admission': current,
              'initial_losses': initial_losses, 'final_losses': final_losses,
              'completed_steps': state['step'], 'scheduler_completed_steps': state['step'],
              'checkpoint_restored_steps': midpoint, 'checkpoint_parameter_max_error': parameter_error,
              'checkpoint_optimizer_max_error': moment_error, 'cpu_metal_max_error': cpu_error,
              'effective_batch_rows': c['batch_size'], 'gradient_accumulation_steps': c['gradient_accumulation_steps'],
              'full_batch_gradient_max_error': gradient_error, 'full_batch_gradient_tolerance': 1e-5,
              'step_log': first + last, 'generated_token_ids': generated, 'generated_text': text,
              'inference_runtime': 'planned_decoder_numpy_cpu', 'pretrained_student_weights_loaded': False,
              'training_approved': True, 'release_approved': False, 'source_initialization_modified': False,
              'workflow_measurements': observed,
              'limitations': 'Small reviewed text corpus, FP32 SGD/AdamW, one/two effective rows and one/two token-weighted microbatches only. Held-out losses are diagnostics; no quality/release gate. Both comparison trajectories execute. Independent continuation, fresh-run cancellation, and mixed precision on this corpus path remain unexposed.',
              'files': {str(path.relative_to(folder)): file_digest(path) for path in folder.rglob('*') if path.is_file()}}
    record['revision'] = digest(record)
    (folder / 'record.json').write_text(json.dumps(record, allow_nan=False, indent=2))
    return read(root, identifier)


def read(root, identifier):
    folder = _folder(root, identifier)
    if (folder / 'record.json').stat().st_size > 256000:
        raise ValueError('Corpus optimizer record exceeds size limit.')
    record = json.loads((folder / 'record.json').read_text()); approved = record['review']; c = configuration(approved['config'], approved['config']['sequence_length'])
    midpoint = c['steps'] // 2
    expected = {'trained-model.json', 'tokenizer.json', *[f'step-{midpoint}/{name}' for name in ('model.json', 'optimizer.json', 'checkpoint.json')]}
    if ((record.get('format'), record.get('schema_version')) not in (('almg-corpus-optimizer-run-v1', 1), ('almg-corpus-optimizer-run-v2', 2)) or record.get('id') != identifier
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
    if record['schema_version'] == 1:
        if c['batch_size'] != 1 or c['gradient_accumulation_steps'] != 1:
            raise ValueError('Legacy corpus runs require their original single-row configuration.')
    else:
        error = record.get('full_batch_gradient_max_error')
        if (record.get('effective_batch_rows') != c['batch_size'] or record.get('gradient_accumulation_steps') != c['gradient_accumulation_steps']
                or c['batch_size'] % c['gradient_accumulation_steps'] or type(error) not in (float, int)
                or not math.isfinite(error) or not 0 <= error <= 1e-5 or record.get('full_batch_gradient_tolerance') != 1e-5
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
    return record


def history(root, initialized, reviewed_inputs):
    saved, _, _, _, _ = _source(root, initialized, reviewed_inputs)
    records = [read(root, path.parent.name) for path in (Path(root) / 'decoder-corpus-optimizer-runs').glob('*/record.json')]
    return sorted([record for record in records if record['review']['corpus_id'] == saved['id']], key=lambda item: item['created_at'])[-20:]
