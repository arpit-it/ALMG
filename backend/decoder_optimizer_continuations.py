"""Independently approved completion of an existing bounded optimizer checkpoint."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import uuid
import numpy as np
if __package__:
    from . import decoder_optimizer_fixture as fixture,decoder_optimizer_continuation_estimates as measured_feedback,decoder_optimizer_cancellations as cancellation
else:
    import decoder_optimizer_fixture as fixture,decoder_optimizer_continuation_estimates as measured_feedback,decoder_optimizer_cancellations as cancellation


def _source(root,identifier):
    parent=fixture.read(root,identifier);c=fixture.configuration(parent['optimizer']);source=parent['review']['source']
    initialized=fixture.initializations.read(root,source['plan_id'],source['initialization_id'])
    admission=fixture.review(root,source['plan_id'],initialized,c)
    return parent,admission,fixture._folder(root,identifier)/f"step-{c['steps']//2}"


def review(root,identifier,resume_id=None):
    parent,admission,checkpoint=_source(root,identifier);c=parent['optimizer'];midpoint=c['steps']//2
    partial=None if resume_id is None else read(root,resume_id)
    if partial is not None and (partial.get('status')!='canceled' or partial['review']['source']['record_id']!=identifier):raise ValueError('Choose a canceled partial checkpoint from this source.')
    restored=midpoint if partial is None else partial['completed_steps']
    snapshot=None if partial is None else _snapshot(partial)
    estimates={**admission['estimates'],'optimizer_work_estimate':None,'isolated_optimizer_memory':None,'pre_continuation_calibration_reserve_bytes':admission['estimates']['required_available_memory_bytes'],'optimizer_updates':c['steps']-restored,
        'checkpoint_step':restored,'recorded_microbatch_backward_calls':(c['steps']-restored)*c.get('gradient_accumulation_steps',1),'reference_comparison_optimizer_updates':0}
    record={'format':'almg-optimizer-continuation-review-v2' if partial is not None else 'almg-optimizer-continuation-review-v1','schema_version':2 if partial is not None else 1,'restore_step':restored,'resume_from':snapshot,
        'source':{'record_id':identifier,'record_revision':parent['revision'],'checkpoint_step':midpoint,
            'checkpoint_sha256':fixture.file_digest(checkpoint/'checkpoint.json'),'optimizer_sha256':fixture.file_digest(checkpoint/'optimizer.json'),
            'trained_model_sha256':parent['files']['trained-model.json']},
        'config':c,'runtime':admission['runtime'],'hardware':admission['hardware'],'estimates':estimates,
        'feasible':admission['feasible'],'blockers':admission['blockers'],'training_approved':False,'release_approved':False,
        'scope':'restore_retained_canceled_partial_and_finish_original_budget' if partial is not None else 'restore_saved_midpoint_and_finish_original_synthetic_budget_in_new_private_artifact',
        'implementation_sha256':fixture.digest({name:fixture.file_digest(Path(__file__).with_name(name)) for name in ('decoder_optimizer_continuations.py','decoder_optimizer_cancellations.py','decoder_optimizer_continuation_estimates.py','decoder_optimizer_isolated.py','decoder_optimizer_worker.py','decoder_optimizer_fixture.py','decoder_optimizer_state.py','decoder_architecture_backward.py','decoder_mixed_precision.py','planned_decoder.py')})}
    memory,work=measured_feedback.feedback(history(root,identifier),record)
    estimates['isolated_optimizer_memory']=memory;estimates['optimizer_work_estimate']=work
    if memory is not None:estimates['required_available_memory_bytes']=max(estimates['required_available_memory_bytes'],memory['calculated_memory_floor_bytes'])
    if not fixture.hardware._fits(record['hardware'],estimates) and not any('memory/disk' in reason for reason in record['blockers']):record['blockers'].append('Current memory/disk does not cover isolated continuation calibration reserves.')
    record['feasible']=not record['blockers']
    record['revision']=fixture.digest(record);return record


def _snapshot(record):
    return {'record_id':record['id'],'record_revision':record['revision'],'model_sha256':record['files']['trained-model.json'],
        'optimizer_sha256':record['files']['optimizer.json'],'completed_steps':record['completed_steps']}


def review_partial(root,identifier):
    partial=read(root,identifier)
    if partial.get('status')!='canceled':raise ValueError('Only a canceled partial checkpoint has remaining work to resume.')
    return review(root,partial['review']['source']['record_id'],identifier)


def run_partial(root,identifier,confirmed,approved,cancel_request_id=None):
    if confirmed is not True:raise ValueError('Explicitly approve resuming the retained partial checkpoint.')
    partial=read(root,identifier)
    if partial.get('status')!='canceled':raise ValueError('Only a canceled partial checkpoint can resume.')
    return run(root,partial['review']['source']['record_id'],True,approved,cancel_request_id,identifier)


def _folder(root,identifier):
    fixture._folder(root,identifier)  # Reuse strict identifier validation, never a caller-provided path.
    return Path(root)/'decoder-optimizer-continuations'/identifier


def run(root,identifier,confirmed,approved,cancel_request_id=None,resume_id=None):
    if confirmed is not True:raise ValueError('Explicitly approve checkpoint continuation and a new private artifact.')
    if cancel_request_id is not None:cancellation.validate(cancel_request_id)
    current=review(root,identifier,resume_id)
    if not isinstance(approved,dict) or approved.get('revision')!=fixture.digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','resume_from','restore_step','config','runtime','estimates','implementation_sha256')):raise ValueError('Checkpoint continuation review changed; reopen it before approval.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Checkpoint continuation is blocked by hardware/resources.')
    parent=fixture.read(root,identifier);c=current['config'];checkpoint=fixture._folder(root,identifier)/f"step-{c['steps']//2}"
    partial=None
    if resume_id is None:
        model,state=fixture.restore(checkpoint,c,parent['review']['revision']);control_id=identifier;control_revision=parent['revision'];control_kind='fixture'
    else:
        partial=read(root,resume_id)
        if _snapshot(partial)!=current['resume_from']:raise ValueError('Retained partial state changed; reopen review.')
        folder=_folder(root,resume_id);model=fixture.PlannedDecoder.load(folder/'trained-model.json');saved=json.loads((folder/'optimizer.json').read_text())
        state={'step':saved['step'],**{kind:{name:np.asarray(value,dtype=np.float32) for name,value in saved[kind].items()} for kind in ('m','v')}}
        control_id=resume_id;control_revision=partial['revision'];control_kind='continuation'
    restored_step=state['step'];shape=model.config
    rows=c.get('batch_size',min(2,shape['batch_size']));length=c.get('sequence_length',min(8,shape['context_length']));accumulation=c.get('gradient_accumulation_steps',1);scale=c.get('loss_scale',1.)
    sequence=np.arange(rows*(length+1)).reshape(rows,length+1)%shape['vocab_size'];x=sequence[:,:-1];y=sequence[:,1:];mask=np.ones_like(y,dtype=np.float32)
    import mlx.core as mx
    with mx.stream(mx.gpu):
        _,loss,gradient=fixture.mixed_precision.functions(shape,mx,scale) if c.get('compute_precision')=='mixed_float16' else fixture.backward.metal_functions(shape,mx)
        def score():return float(loss({name:mx.array(value) for name,value in model.parameters.items()},mx.array(x),mx.array(y),mx.array(mask)).item())
        initial=score();logs=[];cancelled=False
        while state['step']<c['steps']:
            if cancellation.requested(root,control_id,control_revision,cancel_request_id,control_kind):cancelled=True;break
            pieces=[]
            for inputs,targets,weights in zip(np.array_split(x,accumulation),np.array_split(y,accumulation),np.array_split(mask,accumulation)):
                gradients=gradient({name:mx.array(value) for name,value in model.parameters.items()},mx.array(inputs),mx.array(targets),mx.array(weights));mx.eval(gradients)
                pieces.append((fixture.mixed_precision.unscale({name:np.array(value) for name,value in gradients.items()},scale),int(weights.sum())))
            grads=pieces[0][0] if accumulation==1 else fixture.accumulate(pieces)
            model.parameters,state,entry=fixture.update(model.parameters,grads,state,c);entry.update(microbatches=accumulation,target_tokens=int(mask.sum()));logs.append(entry)
        final=score()
    reference=fixture.PlannedDecoder.load(fixture._folder(root,identifier)/'trained-model.json')
    error=None if cancelled else max(float(np.max(np.abs(model.parameters[name]-reference.parameters[name]))) for name in model.parameters)
    generated=fixture._generate(model)
    if not math.isfinite(final) or (not cancelled and (not final<initial or error>1e-7 or generated!=parent['generated_token_ids'])):raise ValueError('Independent continuation failed loss/weight/inference checks; original artifacts remain unchanged.')
    if partial is not None and read(root,resume_id)!=partial:raise ValueError('Retained partial source changed during resume.')
    if fixture.read(root,identifier)!=parent:raise ValueError('Source optimizer run changed during continuation.')
    continuation=uuid.uuid4().hex;directory=_folder(root,continuation);directory.mkdir(parents=True)
    model.save(directory/'trained-model.json');payload={'step':state['step'],'m':{name:value.tolist() for name,value in state['m'].items()},'v':{name:value.tolist() for name,value in state['v'].items()}}
    (directory/'optimizer.json').write_text(json.dumps(payload,allow_nan=False))
    record={'format':'almg-optimizer-continuation-v3' if partial is not None else 'almg-optimizer-continuation-v2','schema_version':3 if partial is not None else 2,'status':'canceled' if cancelled else 'completed',
        'cancellation':{'request_id':cancel_request_id,'honored':cancelled,'checkpoint_step':state['step']} if cancel_request_id is not None else None,'id':continuation,'created_at':datetime.now(timezone.utc).isoformat(),
        'review':current,'approved_review':approved,'restored_steps':restored_step,'completed_steps':state['step'],'scheduler_completed_steps':state['step'],'step_log':logs,
        'initial_train_loss':initial,'final_train_loss':final,'source_final_parameter_max_error':error,'generated_token_ids':generated,
        'training_approved':True,'release_approved':False,'source_modified':False,'pretrained_student_weights_loaded':False,'inference_runtime':'planned_decoder_numpy_cpu',
        'limitations':'Original bounded synthetic budget only. Cooperative cancellation preserves a private partial model and optimizer/scheduler state at an update boundary. Canceled partial artifacts require separate resume approval. General fresh-run cancellation, text corpora and arbitrary OS/process interruption are not yet supported.',
        'files':{name:fixture.file_digest(directory/name) for name in ('trained-model.json','optimizer.json')}}
    record['revision']=fixture.digest(record);(directory/'record.json').write_text(json.dumps(record,allow_nan=False,indent=2));return record


def read(root,identifier,_seen=None):
    seen=set() if _seen is None else set(_seen)
    if identifier in seen or len(seen)>=16:raise ValueError('Partial checkpoint lineage is cyclic or exceeds the bounded depth.')
    seen.add(identifier)
    directory=_folder(root,identifier)
    if (directory/'record.json').stat().st_size>128000 or any((directory/name).stat().st_size>16*1024**2 for name in ('trained-model.json','optimizer.json')):raise ValueError('Continuation artifacts exceed bounded size.')
    record=json.loads((directory/'record.json').read_text())
    if ((record.get('format'),record.get('schema_version')) not in (('almg-optimizer-continuation-v1',1),('almg-optimizer-continuation-v2',2),('almg-optimizer-continuation-v3',3)) or record.get('id')!=identifier
        or record.get('revision')!=fixture.digest({k:v for k,v in record.items() if k!='revision'}) or set(record['files'])!={'trained-model.json','optimizer.json'}
        or any(fixture.file_digest(directory/name)!=sha for name,sha in record['files'].items())):raise ValueError('Continuation artifact binding changed.')
    parent=fixture.read(root,record['review']['source']['record_id']);c=parent['optimizer']
    source=record['review']['source'];midpoint=c['steps']//2;completed=record['completed_steps'];status=record.get('status','completed')
    start=midpoint;snapshot=record['review'].get('resume_from')
    if record['schema_version']==3:
        if not isinstance(snapshot,dict):raise ValueError('Partial resume requires a source snapshot.')
        previous=read(root,snapshot['record_id'],seen)
        if previous.get('status')!='canceled' or previous['review']['source']['record_id']!=parent['id'] or _snapshot(previous)!=snapshot:raise ValueError('Partial checkpoint ancestry changed.')
        start=previous['completed_steps']
    elif snapshot is not None:raise ValueError('Legacy continuation cannot claim partial-resume ancestry.')
    if record['review'].get('restore_step',start)!=start:raise ValueError('Partial restore counter changed.')
    if record['schema_version'] in (2,3) and 'status' not in record:raise ValueError('Version-2 continuation needs a terminal status.')
    if (type(completed) is not int or not start<=completed<=c['steps'] or status not in ('completed','canceled')
        or (status=='completed' and completed!=c['steps']) or (status=='canceled' and (record['schema_version'] not in (2,3) or completed>=c['steps']))):raise ValueError('Invalid continuation terminal status/counter.')
    if status=='canceled':
        intent=record['cancellation'];cancellation.validate(intent['request_id'])
        if intent.get('honored') is not True or intent.get('checkpoint_step')!=completed:raise ValueError('Canceled checkpoint binding changed.')
    if (source['checkpoint_step']!=midpoint or parent['revision']!=source['record_revision'] or record['review']['config']!=c or record['restored_steps']!=start
        or source['checkpoint_sha256']!=parent['files'][f'step-{midpoint}/checkpoint.json']
        or source['optimizer_sha256']!=parent['files'][f'step-{midpoint}/optimizer.json']
        or source['trained_model_sha256']!=parent['files']['trained-model.json']
        or record['scheduler_completed_steps']!=completed
        or [entry['step'] for entry in record['step_log']]!=list(range(start+1,completed+1))):raise ValueError('Source optimizer record or continued scheduler lineage changed.')
    model=fixture.PlannedDecoder.load(directory/'trained-model.json');state=json.loads((directory/'optimizer.json').read_text());expected=set(model.parameters) if c['optimizer']=='adamw' else set()
    if type(state['step']) is not int or state['step']!=completed or record['completed_steps']!=state['step']:raise ValueError('Continuation optimizer/scheduler counter changed.')
    for kind in ('m','v'):
        if set(state[kind])!=expected:raise ValueError('Continuation optimizer moments changed.')
        for name,value in state[kind].items():
            values=np.asarray(value,dtype=np.float32)
            if values.shape!=model.parameters[name].shape or not np.isfinite(values).all() or (kind=='v' and np.any(values<0)):raise ValueError('Invalid continued optimizer state.')
    if model.config!=parent['review']['model_config']:raise ValueError('Continued model configuration changed.')
    if fixture._generate(model)!=record['generated_token_ids'] or (status=='completed' and record['generated_token_ids']!=parent['generated_token_ids']):raise ValueError('Continued CPU inference changed.')
    return record


def history(root,source_id):
    fixture._folder(root,source_id);records=[]
    for path in (Path(root)/'decoder-optimizer-continuations').glob('*/record.json'):
        try:
            record=read(root,path.parent.name)
            if record['review']['source']['record_id']==source_id:records.append(record)
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(records,key=lambda value:value['created_at'])[-20:]
