"""Explicit manual streamed SGD trials with immutable five-step checkpoints."""
import json
from pathlib import Path
import platform
import threading
import uuid
if __package__:
    from . import decoder_stream_learned_windows as windows, decoder_stream_learned_batches as batches, decoder_stream_optimization as core, decoder_bundle, recipe_contracts, training_resources
    from .decoder_stream_training_tokenizer import StreamTrainingTokenizer, SETTINGS
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_learned_windows as windows, decoder_stream_learned_batches as batches, decoder_stream_optimization as core, decoder_bundle, recipe_contracts, training_resources
    from decoder_stream_training_tokenizer import StreamTrainingTokenizer, SETTINGS
    from run_manifest import digest, file_digest
_LOCK=threading.RLock()


def _folder(root,run_id):
    windows._folder(root,run_id)
    return Path(root)/'decoder-stream-training-runs'/run_id


def _implementation():
    return digest({name:file_digest(Path(__file__).with_name(name)) for name in (
        'decoder_stream_training.py','decoder_stream_training_tokenizer.py','decoder_stream_optimization.py',
        'decoder_stream_learned_batches.py','decoder_stream_learned_windows.py','decoder_stream_model_tokenizer.py',
        'decoder_stream_bpe.py','decoder_stream_iterative_bpe.py','decoder_stream_character_bpe.py','decoder_stream_unigram.py',
        'decoder_recipe.py','decoder_bundle.py','decoder_tokenizer.py')})


def review(root,window_id):
    record=windows.read(root,window_id);batches._validated(root,window_id,record)
    return {'windows':record,'settings':dict(SETTINGS),'implementation_sha256':_implementation(),
            'runtime':{'python':platform.python_version(),'mlx':decoder_bundle.version('mlx'),'machine':platform.machine()}}


def _runtime():
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Manual streamed training requires Apple silicon Metal.')
    import mlx.core as mx
    if not mx.metal.is_available():raise ValueError('Metal is unavailable.')
    return mx


def _publish(directory,state):
    state=dict(state);state['revision']=digest({k:v for k,v in state.items() if k!='revision'})
    temporary=directory/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(state,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        temporary.replace(directory/'state.json')
    finally:temporary.unlink(missing_ok=True)
    return state


def _receipt(state,previous):
    return {'kind':'stream_optimizer_checkpoint','schema_version':1,'approval':state['approval'],
            'approval_sha256':digest(state['approval']),'completed_steps':state['completed_steps'],'train_cursor':state['train_cursor'],
            'training_targets':state['training_targets'],'training_loss_sum':state['training_loss_sum'],
            'source_batch_chain_sha256':state['source_batch_chain_sha256'],'previous_checkpoint_sha256':previous,
            'evaluation_sha256':digest(state['evaluation']),'pretrained_weights_loaded':False,'model_training_approved':True,'release_approved':False}


def _checkpoint(root,state,model,tokenizer,previous):
    directory=_folder(root,state['id']);name=f"step-{state['completed_steps']:06d}-{uuid.uuid4().hex}"
    decoder_bundle.save(directory/name,model,tokenizer,_receipt(state,previous),pretraining_stage='pretraining_local')
    state=dict(state,checkpoint=name,checkpoint_manifest_sha256=file_digest(directory/name/'manifest.json'),previous_checkpoint_sha256=previous)
    # Recheck all current source/approval bindings before publishing the new pointer.
    if review(root,state['windows_id'])!=state['review']:raise ValueError('Training review changed; previous checkpoint retained.')
    return _publish(directory,state)


def begin(root,window_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm the separate manual twenty-step streamed training approval.')
    with _LOCK:
        current=review(root,window_id)
        if current!=reviewed:raise ValueError('Reopen the exact stream training review.')
        _runtime()
        resources=training_resources.check_size(65536,Path(root))
        record=current['windows'];source,codec=windows._sources(root,record['comparison_id'],record['overlap_id'],True)
        approval={'version':1,'scope':'manual_stream_sgd20_trial','windows_id':window_id,'windows_revision':record['revision'],
                  'tokenizer_sha256':record['tokenizer_sha256'],'settings':dict(SETTINGS),'implementation_sha256':_implementation()}
        selection={'windows_id':window_id,'windows_revision':record['revision'],'fit_id':record['fit_id'],'fit_revision':source['fit']['revision'],
                   'index_id':record['index_id'],'index_revision':record['index_revision'],'source_sha256':record['source_sha256'],
                   'tokenizer_sha256':record['tokenizer_sha256'],'approval_sha256':digest(approval)}
        tokenizer=StreamTrainingTokenizer(codec.artifact(),selection)
        model=recipe_contracts.initialize_recipe('decoder_from_scratch',{'vocab_size':len(tokenizer.vocabulary),'seed':7})
        state={'format':'almg-stream-training-run-v1','schema_version':1,'id':uuid.uuid4().hex,'windows_id':window_id,
               'review':current,'approval':approval,'status':'paused','completed_steps':0,'train_cursor':None,
               'training_targets':0,'training_loss_sum':0.,'source_batch_chain_sha256':digest([]),'evaluation':None,
               'quality_target_met':False,'release_approved':False,'resources':resources,'cpu_inference_max_error':0.}
        _folder(root,state['id']).mkdir(parents=True)
        return _checkpoint(root,state,model,tokenizer,None)


def read(root,run_id):
    directory=_folder(root,run_id);path=directory/'state.json'
    if path.stat().st_size>512000:raise ValueError('Stream training state is too large.')
    state=json.loads(path.read_text(encoding='utf-8'))
    if (state.get('format')!='almg-stream-training-run-v1' or state.get('schema_version')!=1 or state.get('id')!=run_id
            or state.get('revision')!=digest({k:v for k,v in state.items() if k!='revision'})
            or state.get('release_approved') is not False):raise ValueError('Stream training state changed.')
    name=state['checkpoint']
    if not isinstance(name,str) or Path(name).name!=name or not name.startswith('step-'):raise ValueError('Invalid checkpoint location.')
    if file_digest(directory/name/'manifest.json')!=state['checkpoint_manifest_sha256']:raise ValueError('Stream checkpoint manifest changed.')
    _,_,manifest=decoder_bundle.load(directory/name)
    if manifest['stages']['tokenization']!=4 or manifest['training']!=_receipt(state,state['previous_checkpoint_sha256']):raise ValueError('Stream checkpoint receipt changed.')
    if state['status']!=('complete' if state['completed_steps']==20 else 'paused'):raise ValueError('Stream training status changed.')
    return state


def list_runs(root,window_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm private stream training history review.')
    windows._folder(root,window_id);parent=Path(root)/'decoder-stream-training-runs';result=[]
    for directory in sorted(parent.iterdir()) if parent.exists() else []:
        try:
            state=read(root,directory.name)
            if state['windows_id']==window_id:result.append(state)
        except (OSError,ValueError,TypeError,KeyError):continue
    return result[-20:]


def step(root,run_id,confirmed,expected_revision):
    if confirmed is not True:raise ValueError('Confirm running the next five manual updates now.')
    with _LOCK:
        state=read(root,run_id)
        # Replayed requests must never advance a second checkpoint.
        if expected_revision!=state['revision'] or state['status']=='complete':return state
        if review(root,state['windows_id'])!=state['review']:raise ValueError('Stream training source, runtime or implementation changed; previous checkpoint retained.')
        mx=_runtime();state=dict(state,resources=training_resources.check_size(65536,Path(root)))
        model,tokenizer,_=decoder_bundle.load(_folder(root,run_id)/state['checkpoint'])
        import numpy as np
        with mx.stream(mx.gpu):
            parameters={name:mx.array(value) for name,value in model.parameters.items()}
            logits,loss,gradient=core.metal_functions(model,mx)
            for _ in range(5):
                batch=batches.read_batch(root,state['windows_id'],True,state['review']['windows'],state['train_cursor'],'train',4)
                if not batch['rows'] or batch['real_target_tokens']<=0:raise ValueError('Empty training batch.')
                x=mx.array(batch['inputs']);y=mx.array(batch['targets']);mask=mx.array(batch['loss_mask'],dtype=mx.float32)
                value=float(loss(parameters,x,y,mask).item());grads=gradient(parameters,x,y,mask)
                parameters={key:parameters[key]-.05*grads[key] for key in parameters};mx.eval(parameters)
                if not np.isfinite(value) or value<0:raise ValueError('Nonfinite training loss; previous checkpoint retained.')
                state['completed_steps']+=1;state['training_targets']+=batch['real_target_tokens'];state['training_loss_sum']+=value*batch['real_target_tokens']
                state['train_cursor']=batch['next_cursor'];state['source_batch_chain_sha256']=digest([state['source_batch_chain_sha256'],digest(batch),state['completed_steps']])
            model.parameters={name:np.array(value) for name,value in parameters.items()}
            if not all(np.isfinite(value).all() for value in model.parameters.values()):raise ValueError('Nonfinite parameters; previous checkpoint retained.')
            state['cpu_inference_max_error']=float(np.max(np.abs(model.logits(batch['inputs'])-np.array(logits(parameters,x)))))
            if not np.isfinite(state['cpu_inference_max_error']) or state['cpu_inference_max_error']>=1e-5:raise ValueError('CPU and Metal outputs disagree; previous checkpoint retained.')
            if state['completed_steps']==20:
                def score(batch):
                    px=mx.array(batch['inputs']);py=mx.array(batch['targets']);pm=mx.array(batch['loss_mask'],dtype=mx.float32)
                    scores=logits(parameters,px);correct=mx.take_along_axis(scores,py[...,None],axis=-1).squeeze(-1)
                    return float(mx.sum((mx.logsumexp(scores,axis=-1)-correct)*pm).item()),int(mx.sum((mx.argmax(scores,axis=-1)==py)*pm).item())
                state['evaluation']={split:core.evaluate_split(root,state['windows_id'],state['review']['windows'],split,score,batch_worker=batches) for split in ('validation','test')}
                state['quality_target_met']=all(value['next_token_accuracy']>=.8 for value in state['evaluation'].values())
                state['status']='complete'
        return _checkpoint(root,state,model,tokenizer,state['checkpoint_manifest_sha256'])
