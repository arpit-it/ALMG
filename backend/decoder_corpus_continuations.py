"""Separate approval and immutable lineage for saved corpus midpoint continuation."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid
import numpy as np
if __package__:
    from . import decoder_corpus_optimizer as training
else:
    import decoder_corpus_optimizer as training


def _source(root, identifier):
    parent = training.read(root, identifier)
    origin = parent['review']['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    corpus = training.inputs.read(root, parent['review']['corpus_id'])
    admission = training.review(root, initialized, corpus, parent['review']['config'])
    folder = training._folder(root, identifier) / f"step-{parent['review']['config']['steps'] // 2}"
    return parent, initialized, corpus, admission, folder


def review(root, identifier):
    parent, _, corpus, admission, checkpoint = _source(root, identifier)
    c = admission['config']; restore_step = c['steps'] // 2
    model, state = training.optimizer.restore(checkpoint, c, parent['review']['revision'])
    if model.config != admission['model_config'] or state['step'] != restore_step:
        raise ValueError('Saved corpus checkpoint dimensions/counters changed.')
    estimates = {**admission['estimates'], 'optimizer_updates': c['steps'] - restore_step,
                 'reference_comparison_optimizer_updates': 0, 'restore_step': restore_step}
    record = {'format': 'almg-corpus-continuation-review-v1', 'schema_version': 1,
              'source': {'record_id': identifier, 'record_revision': parent['revision'],
                         'checkpoint_sha256': training.file_digest(checkpoint/'checkpoint.json'),
                         'optimizer_sha256': training.file_digest(checkpoint/'optimizer.json'),
                         'model_sha256': parent['files']['trained-model.json']},
              'corpus_id': corpus['id'], 'corpus_revision': corpus['revision'], 'config': c,
              'restore_step': restore_step, 'runtime': admission['runtime'], 'estimates': estimates,
              'hardware': admission['hardware'], 'feasible': admission['feasible'], 'blockers': admission['blockers'],
              'training_approved': False, 'release_approved': False,
              'scope': 'restore_saved_corpus_midpoint_and_complete_original_budget_in_new_private_artifacts',
              'implementation_sha256': training.digest({'continuation': training.file_digest(Path(__file__)), 'trainer': admission['implementation_sha256']})}
    record['revision'] = training.digest(record)
    return record


def _folder(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Select a saved corpus continuation.')
    return Path(root)/'decoder-corpus-continuations'/identifier


def run(root, identifier, confirmed, approved):
    if confirmed is not True:
        raise ValueError('Explicitly confirm restoring the corpus checkpoint and completing its remaining updates.')
    current = review(root, identifier)
    keys = ('format', 'schema_version', 'source', 'corpus_id', 'corpus_revision', 'config', 'restore_step', 'runtime', 'estimates', 'implementation_sha256')
    if (not isinstance(approved, dict) or approved.get('revision') != training.digest({k:v for k,v in approved.items() if k != 'revision'})
            or any(approved.get(key) != current[key] for key in keys)):
        raise ValueError('Corpus continuation review changed. Reopen it before confirming.')
    if not current['feasible'] or approved.get('feasible') is not True:
        raise ValueError('Corpus continuation is blocked by current hardware/resources.')
    parent, initialized, corpus, _, checkpoint = _source(root, identifier)
    _, _, _, windows, tokenizer = training._source(root, initialized, corpus)
    c = current['config']
    import mlx.core as mx
    observer = training.measurements.OptimizerMeasurements(mx)
    model, state = training.optimizer.restore(checkpoint, c, parent['review']['revision'])
    initial_losses = training.split_losses(model, windows)
    continuation_id = uuid.uuid4().hex; folder = _folder(root, continuation_id); folder.mkdir(parents=True)
    with mx.stream(mx.gpu):
        values, state, logs, gradient_error = training.train_updates(model.parameters, state, c['steps'], windows['train'], c, model.config, mx, observer)
    model.parameters = values
    final_losses = training.split_losses(model, windows)
    reference = training.PlannedDecoder.load(training._folder(root, identifier)/'trained-model.json')
    error = max(float(np.max(np.abs(model.parameters[name] - reference.parameters[name]))) for name in model.parameters)
    generated, text = training._generated(model, tokenizer)
    if (not all(math.isfinite(value) for value in [*initial_losses.values(), *final_losses.values()])
            or final_losses['train'] >= initial_losses['train'] or error > 1e-7
            or generated != parent['generated_token_ids'] or text != parent['generated_text']):
        raise ValueError('Corpus continuation failed loss/reference/inference checks; source artifacts remain unchanged.')
    model.save(folder/'trained-model.json')
    (folder/'optimizer.json').write_text(json.dumps({'step': state['step'], **{kind:{name:value.tolist() for name,value in state[kind].items()} for kind in ('m','v')}}, allow_nan=False))
    (folder/'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
    if training.read(root, identifier) != parent:
        raise ValueError('Source corpus run changed during continuation; new artifacts retained for review.')
    observed = observer.finish(); observed['scope'] = 'corpus_checkpoint_continuation_in_shared_backend'
    observed['limitations'] = 'Shared backend time/RSS/Metal observations include restore, remaining updates, evaluation, model/state saving and CPU generation. There is no uninterrupted retraining trajectory here. Counters may include other work; no isolated peaks or future duration estimate.'
    record = {'format': 'almg-corpus-continuation-v1', 'schema_version': 1, 'id': continuation_id,
              'created_at': datetime.now(timezone.utc).isoformat(), 'review': approved, 'admission': current,
              'restored_step': current['restore_step'], 'completed_steps': state['step'], 'scheduler_completed_steps': state['step'],
              'initial_losses': initial_losses, 'final_losses': final_losses, 'step_log': logs,
              'full_batch_gradient_max_error': gradient_error, 'reference_parameter_max_error': error,
              'generated_token_ids': generated, 'generated_text': text, 'inference_runtime': 'planned_decoder_numpy_cpu',
              'workflow_measurements': observed, 'pretrained_student_weights_loaded': False,
              'source_modified': False, 'training_approved': True, 'release_approved': False,
              'limitations': 'Bounded original-budget continuation only. No independent corpus cancellation, arbitrary interruption or quality/release approval.',
              'files': {name:training.file_digest(folder/name) for name in ('trained-model.json','optimizer.json','tokenizer.json')}}
    record['revision'] = training.digest(record)
    temporary=folder/'.record.tmp'
    temporary.write_text(json.dumps(record, allow_nan=False, indent=2))
    temporary.replace(folder/'record.json')
    return read(root, continuation_id)


def read(root, identifier):
    folder = _folder(root, identifier)
    if (folder/'record.json').stat().st_size > 256000:
        raise ValueError('Corpus continuation record exceeds size limit.')
    record = json.loads((folder/'record.json').read_text()); approved = record['review']
    if (record.get('format') != 'almg-corpus-continuation-v1' or record.get('schema_version') != 1 or record.get('id') != identifier
            or record.get('revision') != training.digest({k:v for k,v in record.items() if k != 'revision'})
            or set(record.get('files',{})) != {'trained-model.json','optimizer.json','tokenizer.json'}
            or any((folder/name).stat().st_size > 16*1024**2 or training.file_digest(folder/name) != sha for name,sha in record['files'].items())
            or approved.get('revision') != training.digest({k:v for k,v in approved.items() if k != 'revision'})):
        raise ValueError('Corpus continuation record/artifact binding changed.')
    parent = training.read(root, approved['source']['record_id']); c = parent['review']['config']; midpoint = c['steps']//2
    checkpoint = training._folder(root,parent['id'])/f'step-{midpoint}'
    if (approved['source']['record_revision'] != parent['revision'] or approved['config'] != c or approved['corpus_id'] != parent['review']['corpus_id']
            or approved['corpus_revision'] != parent['review']['corpus_revision'] or approved['restore_step'] != midpoint
            or any(approved['source'][key] != training.file_digest(checkpoint/name) for key,name in (('checkpoint_sha256','checkpoint.json'),('optimizer_sha256','optimizer.json')))
            or approved['source']['model_sha256'] != parent['files']['trained-model.json']
            or record['restored_step'] != midpoint or record['completed_steps'] != c['steps'] or record['scheduler_completed_steps'] != c['steps']):
        raise ValueError('Corpus continuation source/counter binding changed.')
    model = training.PlannedDecoder.load(folder/'trained-model.json'); state = json.loads((folder/'optimizer.json').read_text())
    expected = set(model.parameters) if c['optimizer']=='adamw' else set()
    if model.config != parent['review']['model_config'] or type(state['step']) is not int or state['step'] != c['steps']:
        raise ValueError('Invalid final corpus optimizer counter or model configuration.')
    for kind in ('m','v'):
        if set(state[kind]) != expected:
            raise ValueError('Missing final corpus optimizer moments.')
        for name, value in state[kind].items():
            array = np.asarray(value,dtype=np.float32)
            if array.shape != model.parameters[name].shape or not np.isfinite(array).all() or (kind=='v' and np.any(array<0)):
                raise ValueError('Invalid final corpus optimizer moments.')
    snapshot_folder = Path(root)/'decoder-corpus-inputs'/approved['corpus_id']
    windows = json.loads((snapshot_folder/'windows.json').read_text())['train']
    if len(record['step_log']) != c['steps']-midpoint:
        raise ValueError('Invalid corpus continuation update count.')
    for step, entry in enumerate(record['step_log'],midpoint):
        indices, arrays = training.batch_arrays(windows,step,c['batch_size'])
        if entry.get('step') != step+1 or entry.get('learning_rate') != training.optimizer.learning_rate(c,step) or entry.get('window_index') != indices[0] or entry.get('window_indices') != indices or entry.get('target_tokens') != int(arrays[2].sum()) or entry.get('microbatches') != c['gradient_accumulation_steps']:
            raise ValueError('Corpus continuation window schedule changed.')
    tokenizer = training.Tokenizer.restore(json.loads((folder/'tokenizer.json').read_text()))
    parent_tokenizer = training.Tokenizer.restore(json.loads((training._folder(root,parent['id'])/'tokenizer.json').read_text()))
    reference = training.PlannedDecoder.load(training._folder(root,parent['id'])/'trained-model.json')
    error = max(float(np.max(np.abs(model.parameters[name]-reference.parameters[name]))) for name in model.parameters)
    gradient_error = record.get('full_batch_gradient_max_error')
    tolerance = 1e-3 if c['compute_precision']=='mixed_float16' else 1e-5
    if (not math.isfinite(error) or error>1e-7 or record['reference_parameter_max_error']!=error
            or type(gradient_error) not in (int,float) or not math.isfinite(gradient_error) or not 0<=gradient_error<=tolerance
            or tokenizer.fingerprint()!=parent_tokenizer.fingerprint()
            or training._generated(model,tokenizer)!=(record['generated_token_ids'],record['generated_text'])
            or record['generated_token_ids']!=parent['generated_token_ids']):
        raise ValueError('Corpus continuation reference weights/tokenizer/inference changed.')
    return record


def history(root, source_id):
    training.read(root,source_id)
    records = [read(root,path.parent.name) for path in (Path(root)/'decoder-corpus-continuations').glob('*/record.json')]
    return sorted([record for record in records if record['review']['source']['record_id']==source_id],key=lambda record:record['created_at'])[-20:]
