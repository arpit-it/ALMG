"""Independently approved completion of an existing bounded optimizer checkpoint."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import uuid
import numpy as np
if __package__:
    from . import decoder_optimizer_fixture as fixture
else:
    import decoder_optimizer_fixture as fixture


def _source(root,identifier):
    parent=fixture.read(root,identifier);c=fixture.configuration(parent['optimizer']);source=parent['review']['source']
    initialized=fixture.initializations.read(root,source['plan_id'],source['initialization_id'])
    admission=fixture.review(root,source['plan_id'],initialized,c)
    return parent,admission,fixture._folder(root,identifier)/f"step-{c['steps']//2}"


def review(root,identifier):
    parent,admission,checkpoint=_source(root,identifier);c=parent['optimizer'];midpoint=c['steps']//2
    estimates={**admission['estimates'],'optimizer_work_estimate':None,'optimizer_updates':c['steps']-midpoint,
        'checkpoint_step':midpoint,'recorded_microbatch_backward_calls':(c['steps']-midpoint)*c.get('gradient_accumulation_steps',1),'reference_comparison_optimizer_updates':0}
    record={'format':'almg-optimizer-continuation-review-v1','schema_version':1,
        'source':{'record_id':identifier,'record_revision':parent['revision'],'checkpoint_step':midpoint,
            'checkpoint_sha256':fixture.file_digest(checkpoint/'checkpoint.json'),'optimizer_sha256':fixture.file_digest(checkpoint/'optimizer.json'),
            'trained_model_sha256':parent['files']['trained-model.json']},
        'config':c,'runtime':admission['runtime'],'hardware':admission['hardware'],'estimates':estimates,
        'feasible':admission['feasible'],'blockers':admission['blockers'],'training_approved':False,'release_approved':False,
        'scope':'restore_saved_midpoint_and_finish_original_synthetic_budget_in_new_private_artifact',
        'implementation_sha256':fixture.digest({name:fixture.file_digest(Path(__file__).with_name(name)) for name in ('decoder_optimizer_continuations.py','decoder_optimizer_fixture.py','decoder_architecture_backward.py','decoder_mixed_precision.py','planned_decoder.py')})}
    record['revision']=fixture.digest(record);return record


def _folder(root,identifier):
    fixture._folder(root,identifier)  # Reuse strict identifier validation, never a caller-provided path.
    return Path(root)/'decoder-optimizer-continuations'/identifier


def run(root,identifier,confirmed,approved):
    if confirmed is not True:raise ValueError('Explicitly approve checkpoint continuation and a new private artifact.')
    current=review(root,identifier)
    if not isinstance(approved,dict) or approved.get('revision')!=fixture.digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','config','runtime','estimates','implementation_sha256')):raise ValueError('Checkpoint continuation review changed; reopen it before approval.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Checkpoint continuation is blocked by hardware/resources.')
    parent=fixture.read(root,identifier);c=current['config'];checkpoint=fixture._folder(root,identifier)/f"step-{c['steps']//2}"
    model,state=fixture.restore(checkpoint,c,parent['review']['revision']);restored_step=state['step'];shape=model.config
    rows=c.get('batch_size',min(2,shape['batch_size']));length=c.get('sequence_length',min(8,shape['context_length']));accumulation=c.get('gradient_accumulation_steps',1);scale=c.get('loss_scale',1.)
    sequence=np.arange(rows*(length+1)).reshape(rows,length+1)%shape['vocab_size'];x=sequence[:,:-1];y=sequence[:,1:];mask=np.ones_like(y,dtype=np.float32)
    import mlx.core as mx
    with mx.stream(mx.gpu):
        _,loss,gradient=fixture.mixed_precision.functions(shape,mx,scale) if c.get('compute_precision')=='mixed_float16' else fixture.backward.metal_functions(shape,mx)
        def score():return float(loss({name:mx.array(value) for name,value in model.parameters.items()},mx.array(x),mx.array(y),mx.array(mask)).item())
        initial=score();logs=[]
        while state['step']<c['steps']:
            pieces=[]
            for inputs,targets,weights in zip(np.array_split(x,accumulation),np.array_split(y,accumulation),np.array_split(mask,accumulation)):
                gradients=gradient({name:mx.array(value) for name,value in model.parameters.items()},mx.array(inputs),mx.array(targets),mx.array(weights));mx.eval(gradients)
                pieces.append((fixture.mixed_precision.unscale({name:np.array(value) for name,value in gradients.items()},scale),int(weights.sum())))
            grads=pieces[0][0] if accumulation==1 else fixture.accumulate(pieces)
            model.parameters,state,entry=fixture.update(model.parameters,grads,state,c);entry.update(microbatches=accumulation,target_tokens=int(mask.sum()));logs.append(entry)
        final=score()
    reference=fixture.PlannedDecoder.load(fixture._folder(root,identifier)/'trained-model.json')
    error=max(float(np.max(np.abs(model.parameters[name]-reference.parameters[name]))) for name in model.parameters)
    generated=fixture._generate(model)
    if not math.isfinite(final) or not final<initial or error>1e-7 or generated!=parent['generated_token_ids']:raise ValueError('Independent continuation failed loss/weight/inference checks; original artifacts remain unchanged.')
    if fixture.read(root,identifier)!=parent:raise ValueError('Source optimizer run changed during continuation.')
    continuation=uuid.uuid4().hex;directory=_folder(root,continuation);directory.mkdir(parents=True)
    model.save(directory/'trained-model.json');payload={'step':state['step'],'m':{name:value.tolist() for name,value in state['m'].items()},'v':{name:value.tolist() for name,value in state['v'].items()}}
    (directory/'optimizer.json').write_text(json.dumps(payload,allow_nan=False))
    record={'format':'almg-optimizer-continuation-v1','schema_version':1,'id':continuation,'created_at':datetime.now(timezone.utc).isoformat(),
        'review':current,'approved_review':approved,'restored_steps':restored_step,'completed_steps':state['step'],'scheduler_completed_steps':state['step'],'step_log':logs,
        'initial_train_loss':initial,'final_train_loss':final,'source_final_parameter_max_error':error,'generated_token_ids':generated,
        'training_approved':True,'release_approved':False,'source_modified':False,'pretrained_student_weights_loaded':False,'inference_runtime':'planned_decoder_numpy_cpu',
        'limitations':'Completes the original bounded synthetic budget from a verified saved midpoint. No text-corpus, extended-budget, arbitrary-interruption or graceful-cancellation claim.',
        'files':{name:fixture.file_digest(directory/name) for name in ('trained-model.json','optimizer.json')}}
    record['revision']=fixture.digest(record);(directory/'record.json').write_text(json.dumps(record,allow_nan=False,indent=2));return record


def read(root,identifier):
    directory=_folder(root,identifier)
    if (directory/'record.json').stat().st_size>128000 or any((directory/name).stat().st_size>16*1024**2 for name in ('trained-model.json','optimizer.json')):raise ValueError('Continuation artifacts exceed bounded size.')
    record=json.loads((directory/'record.json').read_text())
    if (record.get('format')!='almg-optimizer-continuation-v1' or record.get('schema_version')!=1 or record.get('id')!=identifier
        or record.get('revision')!=fixture.digest({k:v for k,v in record.items() if k!='revision'}) or set(record['files'])!={'trained-model.json','optimizer.json'}
        or any(fixture.file_digest(directory/name)!=sha for name,sha in record['files'].items())):raise ValueError('Continuation artifact binding changed.')
    parent=fixture.read(root,record['review']['source']['record_id']);c=parent['optimizer']
    source=record['review']['source'];midpoint=c['steps']//2
    if (parent['revision']!=source['record_revision'] or record['review']['config']!=c or record['restored_steps']!=midpoint
        or source['checkpoint_sha256']!=parent['files'][f'step-{midpoint}/checkpoint.json']
        or source['optimizer_sha256']!=parent['files'][f'step-{midpoint}/optimizer.json']
        or source['trained_model_sha256']!=parent['files']['trained-model.json']
        or record['scheduler_completed_steps']!=c['steps']
        or [entry['step'] for entry in record['step_log']]!=list(range(midpoint+1,c['steps']+1))):raise ValueError('Source optimizer record or continued scheduler lineage changed.')
    model=fixture.PlannedDecoder.load(directory/'trained-model.json');state=json.loads((directory/'optimizer.json').read_text());expected=set(model.parameters) if c['optimizer']=='adamw' else set()
    if type(state['step']) is not int or state['step']!=c['steps'] or record['completed_steps']!=state['step']:raise ValueError('Continuation optimizer/scheduler counter changed.')
    for kind in ('m','v'):
        if set(state[kind])!=expected:raise ValueError('Continuation optimizer moments changed.')
        for name,value in state[kind].items():
            values=np.asarray(value,dtype=np.float32)
            if values.shape!=model.parameters[name].shape or not np.isfinite(values).all() or (kind=='v' and np.any(values<0)):raise ValueError('Invalid continued optimizer state.')
    if fixture._generate(model)!=record['generated_token_ids'] or record['generated_token_ids']!=parent['generated_token_ids']:raise ValueError('Continued CPU inference changed.')
    return record


def history(root,source_id):
    fixture._folder(root,source_id);records=[]
    for path in (Path(root)/'decoder-optimizer-continuations').glob('*/record.json'):
        try:
            record=read(root,path.parent.name)
            if record['review']['source']['record_id']==source_id:records.append(record)
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(records,key=lambda value:value['created_at'])[-20:]
