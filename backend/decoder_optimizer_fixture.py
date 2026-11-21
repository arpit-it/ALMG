"""Versioned bounded SGD/AdamW fixture; separate from all existing trial formats."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
import uuid
import numpy as np
if __package__:
    from . import decoder_architecture_feasibility as hardware,decoder_architecture_initializations as initializations,decoder_architecture_backward as backward,decoder_mixed_precision as mixed_precision,decoder_optimizer_measurements as measurements,decoder_optimizer_estimates as work_estimates
    from .planned_decoder import PlannedDecoder
    from .run_manifest import digest,file_digest
else:
    import decoder_architecture_feasibility as hardware,decoder_architecture_initializations as initializations,decoder_architecture_backward as backward,decoder_mixed_precision as mixed_precision,decoder_optimizer_measurements as measurements,decoder_optimizer_estimates as work_estimates
    from planned_decoder import PlannedDecoder
    from run_manifest import digest,file_digest
DEFAULT={'schema_version':1,'optimizer':'sgd','learning_rate':.01,'schedule':'warmup_cosine','warmup_steps':2,'steps':10,'gradient_clip_norm':1.0,'weight_decay':0.0}


def configuration(values):
    if not isinstance(values,dict):raise ValueError('Provide every versioned optimizer fixture setting.')
    keys=set(DEFAULT)|({'gradient_accumulation_steps'} if values.get('schema_version') in (2,3,4,5,6,7,8,9) else set())
    if values.get('schema_version') in (3,4,5,6,7,8,9):keys|={'compute_precision','loss_scale'}
    if values.get('schema_version')in (4,5,6,7,8,9):keys|={'batch_size','sequence_length'}
    if set(values)!=keys:raise ValueError('Provide every versioned optimizer fixture setting.')
    c=dict(values)
    if type(c['schema_version']) is not int or c['schema_version'] not in (1,2,3,4,5,6,7,8,9) or c['optimizer'] not in ('sgd','adamw') or c['schedule']!='warmup_cosine':raise ValueError('Choose supported versioned SGD or AdamW with warmup/cosine scheduling.')
    if type(c.get('gradient_accumulation_steps',1)) is not int or c.get('gradient_accumulation_steps',1) not in ((1,2,4) if c['schema_version']==9 else (1,2)):raise ValueError('Choose one/two microbatches, or four with version-9 corpus settings.')
    if c['schema_version'] in (4,5,6,7,8,9) and (type(c['batch_size']) is not int or c['batch_size'] not in ((4,) if c['schema_version']==9 else (1,2)) or type(c['sequence_length']) is not int or c['sequence_length'] not in ((16,) if c['schema_version']==8 else (4,8))):raise ValueError('Choose supported corpus batch/sequence: version nine uses four rows and sequence four/eight; version eight uses one/two rows and sixteen tokens.')
    if c.get('compute_precision','float32') not in ('float32','mixed_float16'):raise ValueError('Only FP32 or bounded mixed FP16 computation is supported.')
    if c['schema_version'] in (8,9) and c['compute_precision']!='float32':raise ValueError('Sixteen-token and four-row corpus settings currently require FP32 computation.')
    scale=c.get('loss_scale',1.0);expected=128.0 if c.get('compute_precision')=='mixed_float16' else 1.0
    if type(scale) not in (int,float) or not math.isfinite(scale) or scale!=expected:raise ValueError('Use loss scale 128 for mixed FP16 or 1 for FP32.')
    if type(c['steps']) is not int or c['steps'] not in ((10,20) if c['schema_version'] in (8,9) else (80,) if c['schema_version']==7 else (40,) if c['schema_version']==6 else (10,20) if c['schema_version']==5 else (10,)) or type(c['warmup_steps']) is not int or not 0<=c['warmup_steps']<=3:raise ValueError('Choose ten updates, ten/twenty with version-5 settings, forty with version-6 corpus settings, or eighty with version-7 corpus settings, or ten/twenty with version-8 sixteen-token or version-9 four-row FP32 corpus settings, and zero to three warmup updates.')
    for key,maximum in (('learning_rate',.1),('gradient_clip_norm',10),('weight_decay',.1)):
        value=c[key]
        if type(value) not in (float,int) or not math.isfinite(value) or not (0<=value<=maximum if key=='weight_decay' else 0<value<=maximum):raise ValueError('Invalid finite optimizer setting: '+key)
    if c['optimizer']=='sgd' and c['weight_decay']!=0:raise ValueError('Version-1 SGD does not support weight decay.')
    return c


def learning_rate(c,completed):
    if type(completed) is not int or not 0<=completed<c['steps']:raise ValueError('Invalid optimizer/scheduler step.')
    step=completed+1;warmup=c['warmup_steps']
    if warmup and step<=warmup:return c['learning_rate']*step/warmup
    progress=(step-warmup)/(c['steps']-warmup)
    return c['learning_rate']*(.1+.9*.5*(1+math.cos(math.pi*progress)))



def accumulate(pieces):
    if not pieces:raise ValueError('At least one nonempty gradient microbatch is required.')
    total=0;sums=None
    for gradients,targets in pieces:
        if type(targets) is not int or targets<=0 or not isinstance(gradients,dict) or not gradients:raise ValueError('Microbatches need positive real target-token counts and gradients.')
        values={name:np.asarray(value,dtype=np.float32) for name,value in gradients.items()}
        if any(not np.isfinite(value).all() for value in values.values()):raise ValueError('Nonfinite microbatch gradients cannot accumulate.')
        if sums is None:sums={name:np.zeros_like(value) for name,value in values.items()}
        if set(sums)!=set(values) or any(sums[name].shape!=value.shape for name,value in values.items()):raise ValueError('Microbatch gradient names/shapes must match.')
        try:
            with np.errstate(over='raise',invalid='raise'):
                for name,value in values.items():sums[name]+=value*targets
        except FloatingPointError as error:raise ValueError('Accumulated gradients overflowed; no update is allowed.') from error
        total+=targets
    return {name:(value/total).astype(np.float32) for name,value in sums.items()}


def update(parameters,gradients,state,c):
    c=configuration(c);step=state['step'];rate=learning_rate(c,step)
    if set(gradients)!=set(parameters):raise ValueError('Every trainable parameter needs a gradient.')
    g={name:np.asarray(gradients[name],dtype=np.float32) for name in parameters}
    if any(value.shape!=parameters[name].shape or not np.isfinite(value).all() for name,value in g.items()):raise ValueError('Invalid or nonfinite gradient.')
    norm=math.sqrt(sum(float(np.square(value.astype(np.float64)).sum()) for value in g.values()))
    if not math.isfinite(norm) or norm<=0:raise ValueError('Gradient norm must be finite and nonzero.')
    scale=min(1.0,c['gradient_clip_norm']/norm);g={name:value*scale for name,value in g.items()};next_step=step+1
    moments={'m':{},'v':{}};result={}
    if c['optimizer']=='adamw' and step and (set(state.get('m',{}))!=set(parameters) or set(state.get('v',{}))!=set(parameters)):raise ValueError('AdamW checkpoint needs every first/second moment.')
    for name,value in parameters.items():
        if c['optimizer']=='adamw':
            m=.9*state['m'].get(name,np.zeros_like(value))+.1*g[name];v=.999*state['v'].get(name,np.zeros_like(value))+.001*g[name]*g[name]
            if m.shape!=value.shape or v.shape!=value.shape or not np.isfinite(m).all() or not np.isfinite(v).all() or np.any(v<0):raise ValueError('Invalid AdamW moment state.')
            moments['m'][name]=m.astype(np.float32);moments['v'][name]=v.astype(np.float32)
            direction=(m/(1-.9**next_step))/(np.sqrt(v/(1-.999**next_step))+1e-8)+c['weight_decay']*value
        else:direction=g[name]
        result[name]=(value-rate*direction).astype(np.float32)
        if not np.isfinite(result[name]).all():raise ValueError('Optimizer produced nonfinite weights.')
    return result,{'step':next_step,**moments},{'step':next_step,'learning_rate':rate,'gradient_norm':norm,'clip_scale':scale}


def checkpoint(folder,model,state,c,review_revision):
    folder.mkdir(parents=True,exist_ok=False);model.save(folder/'model.json')
    payload={'step':state['step'],'m':{name:value.tolist() for name,value in state['m'].items()},'v':{name:value.tolist() for name,value in state['v'].items()}}
    (folder/'optimizer.json').write_text(json.dumps(payload,allow_nan=False))
    record={'format':'almg-optimizer-fixture-checkpoint-v1','schema_version':1,'config':c,'review_revision':review_revision,'step':state['step'],
            'files':{name:file_digest(folder/name) for name in ('model.json','optimizer.json')}}
    record['revision']=digest(record);(folder/'checkpoint.json').write_text(json.dumps(record,allow_nan=False));return record


def restore(folder,c,review_revision):
    if (folder/'checkpoint.json').stat().st_size>128000 or any((folder/name).stat().st_size>16*1024**2 for name in ('model.json','optimizer.json')):raise ValueError('Optimizer checkpoint exceeds bounded size.')
    record=json.loads((folder/'checkpoint.json').read_text())
    if (record.get('format')!='almg-optimizer-fixture-checkpoint-v1' or record.get('schema_version')!=1 or record.get('config')!=c
        or record.get('review_revision')!=review_revision or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
        or set(record['files'])!={'model.json','optimizer.json'} or any(file_digest(folder/name)!=sha for name,sha in record['files'].items())):raise ValueError('Optimizer checkpoint binding changed.')
    model=PlannedDecoder.load(folder/'model.json');saved=json.loads((folder/'optimizer.json').read_text());step=saved['step']
    if type(step) is not int or step!=record['step'] or not 0<step<c['steps']:raise ValueError('Invalid restored optimizer/scheduler counter.')
    state={'step':step,**{kind:{name:np.asarray(value,dtype=np.float32) for name,value in saved[kind].items()} for kind in ('m','v')}}
    expected=set(model.parameters) if c['optimizer']=='adamw' else set()
    if any(set(state[kind])!=expected or any(value.shape!=model.parameters[name].shape or not np.isfinite(value).all() or (kind=='v' and np.any(value<0)) for name,value in state[kind].items()) for kind in ('m','v')):raise ValueError('Optimizer moments are missing or invalid.')
    return model,state


def review(root,plan_id,initialized,settings):
    c=configuration(settings)
    if c['schema_version'] in (6,7,8,9):raise ValueError('Corpus-only settings require the reviewed corpus workflow.')
    plan,current,json_bytes=hardware._source(root,plan_id,initialized)
    if current['actual_parameter_count']>16384:raise ValueError('This optimizer fixture supports at most 16384 parameters; save and initialize a smaller plan.')
    profile=hardware.hardware(root);estimates=hardware.estimate(current['config'],json_bytes);moments=current['actual_weight_bytes']*(2 if c['optimizer']=='adamw' else 0)
    estimates.update(optimizer_state_bytes=moments,optimizer_location='numpy_cpu_float32',required_available_memory_bytes=estimates['required_available_memory_bytes']+moments*4,
                     required_free_disk_bytes=estimates['required_free_disk_bytes']+max(2*1024**2,current['actual_weight_bytes']*128))
    effective_rows=c.get('batch_size',min(2,current['config']['batch_size']));length=c.get('sequence_length',min(8,current['config']['context_length']));accumulation=c.get('gradient_accumulation_steps',1)
    estimates.update(optimizer_updates=c['steps'],checkpoint_step=c['steps']//2,recorded_microbatch_backward_calls=c['steps']*accumulation,reference_comparison_optimizer_updates=c['steps'],sequence_length=length,target_tokens_per_update=effective_rows*length,effective_batch_rows=effective_rows,microbatch_rows=effective_rows//accumulation if effective_rows%accumulation==0 else None,gradient_accumulation_steps=accumulation,gradient_accumulation_buffer_bytes=current['actual_weight_bytes'] if accumulation>1 else 0)
    estimates['required_available_memory_bytes']+=current['actual_weight_bytes']*2 if accumulation>1 else 0
    estimates.update(compute_precision=c.get('compute_precision','float32'),master_parameter_dtype='float32',optimizer_state_dtype='float32',loss_scale=c.get('loss_scale',1.0),precision_scope='FP32 conservative reserves are retained; mixed FP16 matrix products do not imply measured memory savings.')
    reasons=list(profile['errors'])
    if effective_rows>current['config']['batch_size'] or length>current['config']['context_length']:reasons.append('Selected batch/sequence exceeds the initialized plan; select a smaller training configuration.')
    if effective_rows%accumulation:reasons.append('Two-way accumulation requires two effective rows; select batch size two and a compatible initialized plan.')
    if profile['system']!='Darwin' or profile['machine']!='arm64' or not profile['metal_available']:reasons.append('Apple silicon with MLX Metal is required for gradients; the optimizer uses FP32 NumPy arrays.')
    if not hardware._fits(profile,estimates):reasons.append('Current memory/disk does not cover optimizer fixture reserves.')
    record={'format':'almg-optimizer-fixture-review-v1','schema_version':1,'source':{'plan_id':plan_id,'initialization_id':current['id'],'initialization_revision':current['revision'],'model_sha256':current['model_sha256']},
        'config':c,'model_config':current['config'],'runtime':work_estimates.runtime(profile),'hardware':profile,'estimates':estimates,'feasible':not reasons,'blockers':reasons,
        'scope':'bounded_synthetic_updates_with_durable_optimizer_and_scheduler_checkpoint_not_general_pretraining','training_approved':False,'release_approved':False,
        'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_optimizer_fixture.py','decoder_optimizer_isolated.py','decoder_optimizer_worker.py','decoder_optimizer_estimates.py','decoder_optimizer_measurements.py','decoder_mixed_precision.py','decoder_architecture_backward.py','planned_decoder.py','decoder_architecture_feasibility.py')})}
    prior=history(root,plan_id,current['id']);estimates['optimizer_work_estimate']=work_estimates.estimate(prior,record)
    estimates['calculated_memory_reserve_bytes']=estimates['required_available_memory_bytes']
    calibration=work_estimates.memory_calibration(prior,record);estimates['isolated_optimizer_memory']=calibration
    if calibration is not None:estimates['required_available_memory_bytes']=max(estimates['required_available_memory_bytes'],calibration['calculated_memory_floor_bytes'])
    if not hardware._fits(profile,estimates) and not any('memory/disk' in reason for reason in reasons):reasons.append('Current memory/disk does not cover isolated optimizer calibration reserves.')
    record['feasible']=not reasons
    record['revision']=digest(record);return record


def _folder(root,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid optimizer fixture ID.')
    return Path(root)/'decoder-optimizer-fixtures'/identifier


def _generate(model):
    tokens=[0]
    for _ in range(10):tokens.append(int(np.argmax(model.logits([tokens[-model.config['context_length']:]])[0,-1])))
    return tokens


def run(root,plan_id,confirmed,initialized,settings,approved):
    if confirmed is not True:raise ValueError('Explicitly approve optimizer fixture training and saved weights/checkpoints.')
    current=review(root,plan_id,initialized,settings)
    if not isinstance(approved,dict) or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','config','model_config','runtime','estimates','implementation_sha256')):raise ValueError('Optimizer review changed; reopen it before training.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Optimizer fixture is blocked by hardware/resources.')
    import mlx.core as mx
    observer=measurements.OptimizerMeasurements(mx)
    model=PlannedDecoder.load(initializations._folder(root,plan_id)/initialized['id']/'model.json');c=current['config'];source={name:value.copy() for name,value in model.parameters.items()};shape=model.config
    rows=c.get('batch_size',min(2,shape['batch_size']));length=c.get('sequence_length',min(8,shape['context_length']));sequence=np.arange(rows*(length+1)).reshape(rows,length+1)%shape['vocab_size'];x=sequence[:,:-1];y=sequence[:,1:];mask=np.ones_like(y,dtype=np.float32)
    identifier=uuid.uuid4().hex;directory=_folder(root,identifier);directory.mkdir(parents=True)
    with mx.stream(mx.gpu):
        fp32_logits,fp32_loss,fp32_gradient=backward.metal_functions(shape,mx);scale=c.get('loss_scale',1.0);precision=c.get('compute_precision','float32')
        logits,loss,gradient=mixed_precision.functions(shape,mx,scale) if precision=='mixed_float16' else (fp32_logits,fp32_loss,fp32_gradient)
        tx=mx.array(x);ty=mx.array(y);tm=mx.array(mask)
        def score(values,shift=0):return float(loss({name:mx.array(value) for name,value in values.items()},mx.array((x+shift)%shape['vocab_size']),mx.array((y+shift)%shape['vocab_size']),tm).item())
        accumulation=c.get('gradient_accumulation_steps',1)
        def full_gradient(values,inputs=tx,targets=ty,weights=tm):
            gradients=gradient({name:mx.array(value) for name,value in values.items()},inputs,targets,weights);mx.eval(gradients)
            return mixed_precision.unscale({name:np.array(value) for name,value in gradients.items()},scale)
        def accumulated_gradient(values):
            if accumulation==1:return full_gradient(values)
            pieces=[]
            for inputs,targets,weights in zip(np.array_split(x,accumulation),np.array_split(y,accumulation),np.array_split(mask,accumulation)):
                pieces.append((full_gradient(values,mx.array(inputs),mx.array(targets),mx.array(weights)),int(weights.sum())))
            return accumulate(pieces)
        original_gradient=full_gradient(source);accumulated=accumulated_gradient(source)
        gradient_error=max(float(np.max(np.abs(original_gradient[name]-accumulated[name]))) for name in original_gradient)
        gradient_tolerance=1e-3 if precision=='mixed_float16' else 1e-5
        if gradient_error>gradient_tolerance:raise ValueError('Accumulated gradients do not match the effective full batch within the selected precision tolerance.')
        def optimize(values,state,end,trajectory):
            logs=[]
            while state['step']<end:
                grads=accumulated_gradient(values)
                values,state,entry=update(values,grads,state,c);entry.update(microbatches=accumulation,target_tokens=int(mask.sum()));logs.append(entry);observer.sample(f"{trajectory}_update_{state['step']}")
            return values,state,logs
        initial=score(source);validation_initial=score(source,1)
        master={name:mx.array(value) for name,value in source.items()};reference_loss=float(fp32_loss(master,tx,ty,tm).item())
        altered=x.copy();cut=max(1,length//2);altered[:,cut:]=(altered[:,cut:]+1)%shape['vocab_size']
        causal_error=float(mx.max(mx.abs(logits(master,tx)[:,:cut]-logits(master,mx.array(altered))[:,:cut])).item())
        if abs(initial-reference_loss)>.05 or causal_error>1e-5:raise ValueError('Selected precision failed initial FP32-loss or causal-prefix compatibility.')
        empty={'step':0,'m':{},'v':{}};midpoint=c['steps']//2;checkpoint_path=directory/f'step-{midpoint}'
        uninterrupted,reference_state,_=optimize(source,empty,c['steps'],'reference')
        halfway,state,first=optimize(source,empty,midpoint,'checkpointed');model.parameters=halfway;checkpoint(checkpoint_path,model,state,c,current['revision'])
        restored,state=restore(checkpoint_path,c,current['revision']);parameters,state,last=optimize(restored.parameters,state,c['steps'],'resumed')
        resume_error=max(float(np.max(np.abs(parameters[name]-uninterrupted[name]))) for name in parameters)
        moment_error=max([0.0]+[float(np.max(np.abs(state[kind][name]-reference_state[kind][name]))) for kind in ('m','v') for name in state[kind]])
        final=score(parameters);validation_final=score(parameters,1)
    if not math.isfinite(final) or not final<initial or resume_error>1e-7 or moment_error>1e-7:raise ValueError('Optimizer fixture failed loss/resume checks; any saved checkpoint is retained.')
    model.parameters=parameters;model.save(directory/'trained-model.json');loaded=PlannedDecoder.load(directory/'trained-model.json')
    generated=_generate(loaded);observed=observer.finish()
    if initializations.read(root,plan_id,initialized['id'])!=initialized or file_digest(initializations._folder(root,plan_id)/initialized['id']/'model.json')!=current['source']['model_sha256']:raise ValueError('Source initialization changed during optimizer training; retained artifacts need review.')
    record={'format':'almg-decoder-optimizer-fixture-v1','schema_version':1,'id':identifier,'created_at':datetime.now(timezone.utc).isoformat(),'review':current,'approved_review':approved,
        'workflow_measurements':observed,'initial_train_loss':initial,'final_train_loss':final,'initial_validation_loss':validation_initial,'final_validation_loss':validation_final,
        'compute_precision':precision,'master_parameter_dtype':'float32','master_gradient_dtype':'float32','optimizer_state_dtype':'float32','loss_scale':scale,'initial_fp32_reference_loss':reference_loss,'initial_precision_loss_difference':abs(initial-reference_loss),'causal_prefix_max_error':causal_error,'full_batch_gradient_tolerance':gradient_tolerance,'optimizer':c,'gradient_accumulation_steps':accumulation,'effective_batch_rows':rows,'sequence_length':length,'target_tokens_per_update':int(mask.sum()),'microbatch_rows':rows//accumulation,'full_batch_gradient_max_error':gradient_error,'microbatch_backward_calls_in_recorded_trajectory':c['steps']*accumulation,'completed_steps':state['step'],'scheduler_completed_steps':state['step'],'step_log':first+last,'checkpoint_restored_steps':midpoint,'checkpoint_optimizer_max_error':moment_error,'checkpoint_parameter_max_error':resume_error,
        'generated_token_ids':generated,'inference_runtime':'planned_decoder_numpy_cpu','pretrained_student_weights_loaded':False,'updated_weights_saved':True,'initialization_modified':False,'training_approved':True,'release_approved':False,
        'limitations':'Generated token-ID smoke fixture only; no text corpus/tokenizer, full-epoch training, general model quality, large-model or general mixed-precision claim. Mixed FP16 is validated only for this bounded fixture with fixed loss scaling. Saved midpoint continuation requires separate approval and supports cooperative cancellation; fresh-run cancellation is not exposed.',
        'files':{str(path.relative_to(directory)):file_digest(path) for path in directory.rglob('*') if path.is_file()}}
    record['revision']=digest(record);(directory/'record.json').write_text(json.dumps(record,allow_nan=False,indent=2));return record


def read(root,identifier):
    directory=_folder(root,identifier)
    if (directory/'record.json').stat().st_size>128000:raise ValueError('Optimizer fixture record exceeds size limit.')
    record=json.loads((directory/'record.json').read_text());c=configuration(record['optimizer']);checkpoint_name=f"step-{c['steps']//2}"
    if (record.get('format')!='almg-decoder-optimizer-fixture-v1' or record.get('schema_version')!=1 or record.get('id')!=identifier or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
        or set(record['files'])!={f'{checkpoint_name}/model.json',f'{checkpoint_name}/optimizer.json',f'{checkpoint_name}/checkpoint.json','trained-model.json'}
        or any(file_digest(directory/name)!=sha for name,sha in record['files'].items()) or _generate(PlannedDecoder.load(directory/'trained-model.json'))!=record['generated_token_ids']):raise ValueError('Optimizer fixture artifact or inference binding changed.')
    restore(directory/checkpoint_name,c,record['review']['revision'])
    return record


def history(root,plan_id,initialization_id):
    records=[]
    for path in (Path(root)/'decoder-optimizer-fixtures').glob('*/record.json'):
        try:
            record=read(root,path.parent.name)
            if record['review']['source']['plan_id']==plan_id and record['review']['source']['initialization_id']==initialization_id:records.append(record)
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(records,key=lambda value:value['created_at'])[-20:]
