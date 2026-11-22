"""Separate approval and immutable lineage for saved corpus midpoint continuation."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid
import numpy as np
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_cancellations as cancellation, decoder_corpus_continuation_feedback as measured_feedback
else:
    import decoder_corpus_optimizer as training, decoder_corpus_cancellations as cancellation, decoder_corpus_continuation_feedback as measured_feedback


def _source(root, identifier):
    parent = training.read(root, identifier)
    if parent.get('status','completed')!='completed':raise ValueError('A canceled fresh corpus run does not support midpoint continuation yet.')
    origin = parent['review']['source']
    initialized = training.hardware.initializations.read(root, origin['plan_id'], origin['initialization_id'])
    corpus = training.inputs.read(root, parent['review']['corpus_id'])
    admission = training.review(root, initialized, corpus, parent['review']['config'])
    folder = training._folder(root, identifier) / f"step-{parent['review']['config']['steps'] // 2}"
    return parent, initialized, corpus, admission, folder


def _depth(record):
    return record['lineage_depth'] if record['schema_version']==3 else 1


def _snapshot(record):
    return {'record_id':record['id'],'record_revision':record['revision'],
            'model_sha256':record['files']['trained-model.json'],'optimizer_sha256':record['files']['optimizer.json'],
            'completed_steps':record['completed_steps'],'lineage_depth':_depth(record)}


def _load_state(folder, model, config):
    saved=json.loads((folder/'optimizer.json').read_text())
    version=2 if isinstance(saved,dict) and 'format' in saved else 1
    return training.optimizer.optimizer_state.decode(saved,model.parameters,config,version=version,allow_completed=True)


def _partial_state(root, record):
    folder=_folder(root,record['id']);model=training.PlannedDecoder.load(folder/'trained-model.json')
    return model,_load_state(folder,model,record['review']['config'])


def review(root, identifier, resume_id=None, execution_mode='shared_backend'):
    if execution_mode not in ('shared_backend','fresh_process'):raise ValueError('Choose a supported corpus continuation execution mode.')
    parent, _, corpus, admission, checkpoint = _source(root, identifier)
    c = admission['config']; partial=None if resume_id is None else read(root,resume_id)
    if partial is not None and (partial.get('status')!='canceled' or partial['review']['source']['record_id']!=identifier or _depth(partial)>=16):
        raise ValueError('Select a canceled partial from this original corpus run with fewer than sixteen ancestors.')
    restore_step=c['steps']//2 if partial is None else partial['completed_steps']
    model,state=training.optimizer.restore(checkpoint,c,parent['review']['revision']) if partial is None else _partial_state(root,partial)
    if model.config != admission['model_config'] or state['step'] != restore_step:
        raise ValueError('Saved corpus checkpoint dimensions/counters changed.')
    estimates = {**admission['estimates'], 'optimizer_updates': c['steps'] - restore_step,
                 'reference_comparison_optimizer_updates': 0, 'restore_step': restore_step}
    record = {'format': ('almg-corpus-continuation-review-v3' if partial is None else 'almg-corpus-continuation-review-v4') if execution_mode=='fresh_process' else ('almg-corpus-continuation-review-v1' if partial is None else 'almg-corpus-continuation-review-v2'), 'schema_version': (3 if partial is None else 4) if execution_mode=='fresh_process' else (1 if partial is None else 2),
              'execution_mode':execution_mode,
              'resume_from':None if partial is None else _snapshot(partial),
              'source': {'record_id': identifier, 'record_revision': parent['revision'],
                         'checkpoint_sha256': training.file_digest(checkpoint/'checkpoint.json'),
                         'optimizer_sha256': training.file_digest(checkpoint/'optimizer.json'),
                         'model_sha256': parent['files']['trained-model.json']},
              'corpus_id': corpus['id'], 'corpus_revision': corpus['revision'], 'config': c,
              'restore_step': restore_step, 'runtime': admission['runtime'], 'estimates': estimates,
              'hardware': admission['hardware'], 'feasible': admission['feasible'], 'blockers': admission['blockers'],
              'training_approved': False, 'release_approved': False,
              'scope': 'restore_saved_corpus_midpoint_and_complete_original_budget_in_new_private_artifacts' if partial is None else 'restore_retained_corpus_partial_and_complete_original_remaining_updates',
              'implementation_sha256': training.digest({'continuation': training.file_digest(Path(__file__)), 'cancellation': training.file_digest(Path(__file__).with_name('decoder_corpus_cancellations.py')), 'feedback':training.file_digest(Path(__file__).with_name('decoder_corpus_continuation_feedback.py')), 'trainer': admission['implementation_sha256']})}
    estimates['calculated_memory_reserve_bytes']=estimates['required_available_memory_bytes']
    memory,work=measured_feedback.feedback(history(root,identifier),record) if execution_mode=='fresh_process' else (None,None)
    estimates['isolated_continuation_memory']=memory;estimates['corpus_continuation_work_estimate']=work
    training.feedback.apply_memory_floor(estimates,memory)
    if not training.hardware._fits(record['hardware'],estimates) and not any('memory/disk' in reason for reason in record['blockers']):record['blockers'].append('Current memory/disk or Metal working-set recommendation does not cover isolated corpus continuation calibration reserves.')
    record['feasible']=not record['blockers']
    record['revision'] = training.digest(record)
    return record


def _folder(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Select a saved corpus continuation.')
    return Path(root)/'decoder-corpus-continuations'/identifier


def run(root, identifier, confirmed, approved, request_id=None, resume_id=None, execution_mode='shared_backend'):
    if confirmed is not True:
        raise ValueError('Explicitly confirm restoring the corpus checkpoint and completing its remaining updates.')
    if request_id is not None:
        cancellation.validate(request_id)
    current = review(root, identifier, resume_id, execution_mode)
    keys = ('format', 'schema_version', 'source', 'corpus_id', 'corpus_revision', 'config', 'restore_step', 'resume_from', 'runtime', 'estimates', 'implementation_sha256', 'execution_mode')
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
    partial=None if resume_id is None else read(root,resume_id)
    model,state=training.optimizer.restore(checkpoint,c,parent['review']['revision']) if partial is None else _partial_state(root,partial)
    cancel_id=identifier if partial is None else partial['id'];cancel_revision=parent['revision'] if partial is None else partial['revision'];cancel_kind='run' if partial is None else 'partial'
    initial_losses = training.split_losses(model, windows)
    continuation_id = uuid.uuid4().hex; folder = _folder(root, continuation_id); folder.mkdir(parents=True)
    with mx.stream(mx.gpu):
        values, state, logs, gradient_error = training.train_updates(model.parameters, state, c['steps'], windows['train'], c, model.config, mx, observer,
            stop=lambda: cancellation.requested(root,cancel_id,cancel_revision,request_id,cancel_kind))
    model.parameters = values
    final_losses = training.split_losses(model, windows)
    reference = training.PlannedDecoder.load(training._folder(root, identifier)/'trained-model.json')
    canceled = state['step'] < c['steps']
    error = None if canceled else max(float(np.max(np.abs(model.parameters[name] - reference.parameters[name]))) for name in model.parameters)
    generated, text = training._generated(model, tokenizer)
    if (not all(math.isfinite(value) for value in [*initial_losses.values(), *final_losses.values()])
            or (not canceled and (final_losses['train'] >= initial_losses['train'] or error > 1e-7
                or generated != parent['generated_token_ids'] or text != parent['generated_text']))):
        raise ValueError('Corpus continuation failed loss/reference/inference checks; source artifacts remain unchanged.')
    model.save(folder/'trained-model.json')
    payload=training.optimizer.optimizer_state.encode(state,model.parameters,c,compact=sum(value.size for value in model.parameters.values())>16384,allow_completed=True)
    (folder/'optimizer.json').write_text(json.dumps(payload,allow_nan=False))
    (folder/'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
    if (partial is not None and read(root,resume_id)!=partial) or training.read(root, identifier) != parent:
        raise ValueError('Source corpus run changed during continuation; new artifacts retained for review.')
    observed = observer.finish(); observed['scope'] = 'corpus_checkpoint_continuation_in_shared_backend'
    if execution_mode=='fresh_process':observed['scope']='phase_samples_inside_isolated_corpus_continuation'
    observed['limitations'] = ('Synchronized phase samples inside one fresh recovery worker; lifetime peaks are reported separately when published. Sampling starts after admission and excludes bootstrap/lineage admission. Includes restore, remaining updates, saved state and CPU generation; no uninterrupted retraining trajectory or total wall-time estimate.' if execution_mode=='fresh_process' else 'Shared backend time/RSS/Metal observations include restore, remaining updates, evaluation, model/state saving and CPU generation. There is no uninterrupted retraining trajectory here. Counters may include other work; no isolated peaks or future duration estimate.')
    record = {'format': 'almg-corpus-continuation-v2' if partial is None else 'almg-corpus-continuation-v3', 'schema_version': 2 if partial is None else 3,
              'lineage_depth':1 if partial is None else _depth(partial)+1, 'id': continuation_id,
              'status': 'canceled' if canceled else 'completed', 'request_id': request_id,
              'created_at': datetime.now(timezone.utc).isoformat(), 'review': approved, 'admission': current,
              'restored_step': current['restore_step'], 'completed_steps': state['step'], 'scheduler_completed_steps': state['step'],
              'initial_losses': initial_losses, 'final_losses': final_losses, 'step_log': logs,
              'full_batch_gradient_max_error': gradient_error, 'reference_parameter_max_error': error,
              'generated_token_ids': generated, 'generated_text': text, 'inference_runtime': 'planned_decoder_numpy_cpu',
              'workflow_measurements': observed, 'pretrained_student_weights_loaded': False,
              'source_modified': False, 'training_approved': True, 'release_approved': False,
              'limitations': 'Bounded original-budget continuation with cooperative cancellation only. Canceled model/state/counter remain private; Partial resume requires separate approval and preserves ancestors. Arbitrary interruption and quality/release approval remain unexposed.',
              'files': {name:training.file_digest(folder/name) for name in ('trained-model.json','optimizer.json','tokenizer.json')}}
    record['revision'] = training.digest(record)
    temporary=folder/'.record.tmp'
    temporary.write_text(json.dumps(record, allow_nan=False, indent=2))
    temporary.replace(folder/'record.json')
    return read(root, continuation_id)


def read(root, identifier, _seen=None):
    folder=_folder(root,identifier)
    seen=set() if _seen is None else set(_seen)
    if identifier in seen or len(seen)>=16:raise ValueError('Cyclic or over-depth corpus partial lineage.')
    seen.add(identifier)
    if (folder/'record.json').stat().st_size > 256000:
        raise ValueError('Corpus continuation record exceeds size limit.')
    record = json.loads((folder/'record.json').read_text()); approved = record['review']
    training.validate_batch_losses(record)
    if ((record.get('format'),record.get('schema_version')) not in (('almg-corpus-continuation-v1',1),('almg-corpus-continuation-v2',2),('almg-corpus-continuation-v3',3)) or record.get('id') != identifier
            or record.get('revision') != training.digest({k:v for k,v in record.items() if k != 'revision'})
            or set(record.get('files',{})) != {'trained-model.json','optimizer.json','tokenizer.json'}
            or any((folder/name).stat().st_size > 16*1024**2 or training.file_digest(folder/name) != sha for name,sha in record['files'].items())
            or approved.get('revision') != training.digest({k:v for k,v in approved.items() if k != 'revision'})):
        raise ValueError('Corpus continuation record/artifact binding changed.')
    parent = training.read(root, approved['source']['record_id']); c = parent['review']['config']; midpoint = c['steps']//2
    snapshot=approved.get('resume_from');partial=None
    if record['schema_version']==3:
        if not isinstance(snapshot,dict):raise ValueError('Missing retained corpus partial lineage.')
        partial=read(root,snapshot.get('record_id'),seen)
        if (partial.get('status')!='canceled' or partial['review']['source']['record_id']!=parent['id'] or snapshot!=_snapshot(partial)
                or record.get('lineage_depth')!=_depth(partial)+1 or record['lineage_depth']>16):
            raise ValueError('Retained corpus partial source binding changed.')
    elif snapshot is not None:raise ValueError('Legacy corpus continuations cannot claim partial ancestry.')
    restored=midpoint if partial is None else partial['completed_steps']
    cancel_id=parent['id'] if partial is None else partial['id'];cancel_revision=parent['revision'] if partial is None else partial['revision'];cancel_kind='run' if partial is None else 'partial'
    status = record.get('status') if record['schema_version']>=2 else 'completed'
    if record['schema_version']>=2 and 'request_id' not in record:
        raise ValueError('Missing corpus continuation request binding.')
    if record['schema_version']>=2 and record.get('request_id') is not None:
        cancellation.validate(record['request_id'])
    completed = record['completed_steps']
    if (status not in ('completed','canceled') or type(completed) is not int
            or (status=='completed' and completed!=c['steps']) or (status=='canceled' and not restored<=completed<c['steps'])
            or (status=='canceled' and (record.get('request_id') is None or not cancellation.requested(root,cancel_id,cancel_revision,record['request_id'],cancel_kind)))):
        raise ValueError('Invalid corpus continuation cancellation status or retained counter.')
    checkpoint = training._folder(root,parent['id'])/f'step-{midpoint}'
    if (approved['source']['record_revision'] != parent['revision'] or approved['config'] != c or approved['corpus_id'] != parent['review']['corpus_id']
            or approved['corpus_revision'] != parent['review']['corpus_revision'] or approved['restore_step'] != restored
            or any(approved['source'][key] != training.file_digest(checkpoint/name) for key,name in (('checkpoint_sha256','checkpoint.json'),('optimizer_sha256','optimizer.json')))
            or approved['source']['model_sha256'] != parent['files']['trained-model.json']
            or record['restored_step'] != restored or record['scheduler_completed_steps'] != completed):
        raise ValueError('Corpus continuation source/counter binding changed.')
    model = training.PlannedDecoder.load(folder/'trained-model.json'); state = _load_state(folder,model,c)
    if model.config != parent['review']['model_config'] or state['step'] != completed:
        raise ValueError('Invalid final corpus optimizer counter or model configuration.')
    snapshot_folder = Path(root)/'decoder-corpus-inputs'/approved['corpus_id']
    windows = json.loads((snapshot_folder/'windows.json').read_text())['train']
    if len(record['step_log']) != completed-restored:
        raise ValueError('Invalid corpus continuation update count.')
    for step, entry in enumerate(record['step_log'],restored):
        indices, arrays = training.batch_arrays(windows,step,c['batch_size'])
        if entry.get('step') != step+1 or entry.get('learning_rate') != training.optimizer.learning_rate(c,step) or entry.get('window_index') != indices[0] or entry.get('window_indices') != indices or entry.get('target_tokens') != int(arrays[2].sum()) or entry.get('microbatches') != c['gradient_accumulation_steps']:
            raise ValueError('Corpus continuation window schedule changed.')
    tokenizer = training.Tokenizer.restore(json.loads((folder/'tokenizer.json').read_text()))
    parent_tokenizer = training.Tokenizer.restore(json.loads((training._folder(root,parent['id'])/'tokenizer.json').read_text()))
    reference = training.PlannedDecoder.load(training._folder(root,parent['id'])/'trained-model.json')
    error = max(float(np.max(np.abs(model.parameters[name]-reference.parameters[name]))) for name in model.parameters)
    gradient_error = record.get('full_batch_gradient_max_error')
    tolerance = 1e-3 if c['compute_precision']=='mixed_float16' else 1e-5
    if ((status=='completed' and (not math.isfinite(error) or error>1e-7 or record['reference_parameter_max_error']!=error))
            or (status=='canceled' and record['reference_parameter_max_error'] is not None)
            or type(gradient_error) not in (int,float) or not math.isfinite(gradient_error) or not 0<=gradient_error<=tolerance
            or tokenizer.fingerprint()!=parent_tokenizer.fingerprint()
            or training._generated(model,tokenizer)!=(record['generated_token_ids'],record['generated_text'])
            or (status=='completed' and record['generated_token_ids']!=parent['generated_token_ids'])):
        raise ValueError('Corpus continuation reference weights/tokenizer/inference changed.')
    if 'isolated_workflow_measurements' in record:
        if approved.get('execution_mode')!='fresh_process' or measured_feedback.measurements(record) is None:raise ValueError('Corpus continuation isolation measurements lack matching execution policy.')
    return record


def history(root, source_id):
    training.read(root,source_id)
    records = [read(root,path.parent.name) for path in (Path(root)/'decoder-corpus-continuations').glob('*/record.json')]
    return sorted([record for record in records if record['review']['source']['record_id']==source_id],key=lambda record:record['created_at'])[-20:]


def review_partial(root, identifier, execution_mode='shared_backend'):
    partial=read(root,identifier)
    return review(root,partial['review']['source']['record_id'],identifier,execution_mode)


def run_partial(root, identifier, confirmed, approved, request_id=None, execution_mode='shared_backend'):
    if confirmed is not True:raise ValueError('Explicitly confirm retained corpus partial resume.')
    partial=read(root,identifier)
    return run(root,partial['review']['source']['record_id'],True,approved,request_id,identifier,execution_mode)
