"""Fresh corpus run cancellation, retaining the active verification/training state."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import threading
import numpy as np
if __package__:
    from .run_manifest import digest, file_digest
else:
    from run_manifest import digest, file_digest
_LOCK=threading.Lock()


def validate(identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Use a bounded corpus run token.')
    return identifier


def _binding(review):
    if not isinstance(review,dict) or review.get('revision')!=digest({k:v for k,v in review.items() if k!='revision'}):raise ValueError('Reopen the exact corpus run review.')
    source=review.get('source',{})
    if not isinstance(source,dict):raise ValueError('Invalid fresh corpus source binding.')
    for value in (source.get('plan_id'),source.get('initialization_id'),review.get('corpus_id')):validate(value)
    return {'review_revision':review['revision'],'plan_id':source['plan_id'],'initialization_id':source['initialization_id'],'corpus_id':review['corpus_id'],'corpus_revision':review['corpus_revision']}


def _path(root,token):return Path(root)/'decoder-corpus-run-cancellation-requests'/(validate(token)+'.json')


def _read(path):
    if path.stat().st_size>16384:raise ValueError('Fresh corpus cancellation receipt exceeds size limit.')
    record=json.loads(path.read_text())
    if (record.get('format')!='almg-corpus-run-cancellation-v1' or record.get('schema_version')!=1 or record.get('cancel_requested') is not True
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):raise ValueError('Fresh corpus cancellation receipt changed.')
    return record


def request(root,review,token,confirmed):
    if confirmed is not True:raise ValueError('Explicitly request cancellation of this fresh corpus run.')
    binding=_binding(review);path=_path(root,token)
    with _LOCK:
        if path.exists():
            record=_read(path)
            if record['request_id']!=token or record['binding']!=binding:raise ValueError('Fresh run token belongs to another review.')
            return record
        record={'format':'almg-corpus-run-cancellation-v1','schema_version':1,'request_id':token,'binding':binding,'cancel_requested':True,'created_at':datetime.now(timezone.utc).isoformat()}
        record['revision']=digest(record);path.parent.mkdir(parents=True,exist_ok=True)
        with NamedTemporaryFile(mode='w',dir=path.parent,prefix='.cancel-',delete=False) as output:
            json.dump(record,output,allow_nan=False);temporary=Path(output.name)
        temporary.replace(path);return record


def requested(root,review,token):
    if token is None:return False
    path=_path(root,token)
    if not path.exists():return False
    record=_read(path)
    if record['request_id']!=token or record['binding']!=_binding(review):raise ValueError('Fresh run cancellation review/token binding changed.')
    return True


class Stopped(Exception):
    def __init__(self,values,state,logs,phase):
        self.values,self.state,self.logs,self.phase=values,state,logs,phase


def _training():
    if __package__:from . import decoder_corpus_optimizer
    else:import decoder_corpus_optimizer
    return decoder_corpus_optimizer


def _save_state(path,state):
    path.write_text(json.dumps({'step':state['step'],**{kind:{name:value.tolist() for name,value in state[kind].items()} for kind in ('m','v')}},allow_nan=False))


def save(root,folder,identifier,initialized,corpus,approved,current,model,tokenizer,windows,initial,event,reference,reference_state,reference_log,first,observer,token,checkpoint_owner=None):
    training=_training();c=current['config'];training._source(root,initialized,corpus)
    if checkpoint_owner is None and not requested(root,approved,token):raise ValueError('Missing confirmed fresh-run cancellation.')
    model.parameters=event.values;final=training.split_losses(model,windows)
    if not all(math.isfinite(value) for value in [*initial.values(),*final.values()]):raise ValueError('Canceled corpus state has nonfinite losses; artifacts require review.')
    model.save(folder/'trained-model.json');_save_state(folder/'optimizer.json',event.state)
    (folder/'tokenizer.json').write_text(json.dumps(tokenizer.artifact(),ensure_ascii=False),encoding='utf-8')
    if event.phase=='checkpointed_training':
        reference_model=training.PlannedDecoder(model.config);reference_model.parameters=reference
        reference_model.save(folder/'reference-model.json');_save_state(folder/'reference-optimizer.json',reference_state)
    generated,text=training._generated(model,tokenizer);midpoint=c['steps']//2
    observed=observer.finish();observed['scope']='canceled_corpus_phase_in_fresh_worker' if approved.get('execution_mode')=='fresh_process' else 'canceled_corpus_phase_in_shared_backend'
    observed['limitations']='Synchronized samples for the canceled active phase and prior verification work; not completed training, isolated lifetime peaks or future-duration evidence. Fresh-process lifetime peaks are separate when published.'
    record={'format':'almg-corpus-optimizer-run-v4','schema_version':4,'id':identifier,'created_at':datetime.now(timezone.utc).isoformat(),
            'status':'canceled','request_id':token,'review':approved,'admission':current,'cancellation_phase':event.phase,
            'completed_steps':event.state['step'],'scheduler_completed_steps':event.state['step'],
            'reference_completed_steps':event.state['step'] if event.phase=='reference_verification' else c['steps'],
            'recorded_training_updates':0 if event.phase=='reference_verification' else event.state['step'],
            'checkpoint_restored_steps':midpoint if (folder/f'step-{midpoint}').exists() else 0,
            'initial_losses':initial,'final_losses':final,'step_log':event.logs if event.phase=='reference_verification' else first+event.logs,
            'reference_step_log':event.logs if event.phase=='reference_verification' else reference_log,
            'effective_batch_rows':c['batch_size'],'gradient_accumulation_steps':c['gradient_accumulation_steps'],
            'compute_precision':c['compute_precision'],'loss_scale':c['loss_scale'],'master_parameter_dtype':'float32','optimizer_state_dtype':'float32',
            'generated_token_ids':generated,'generated_text':text,'inference_runtime':'planned_decoder_numpy_cpu',
            'workflow_measurements':observed,'reference_verified':False,'pretrained_student_weights_loaded':False,
            'training_approved':True,'release_approved':False,'source_initialization_modified':False,
            'limitations':'Canceled active phase only; actual state/counters and any completed reference/checkpoint retained privately. No completed comparison, loss/quality gate or release approval. Reference-phase resume requires separate approval; recorded-training partial resume requires its own exact-state approval.',
            'files':{str(path.relative_to(folder)):file_digest(path) for path in folder.rglob('*') if path.is_file()}}
    if __package__:from . import decoder_corpus_reference_resume
    else:import decoder_corpus_reference_resume
    record.update(decoder_corpus_reference_resume.metadata(approved,record['reference_completed_steps']))
    if __package__:from . import decoder_corpus_training_resume
    else:import decoder_corpus_training_resume
    record.update(decoder_corpus_training_resume.metadata(approved,record['completed_steps']))
    if checkpoint_owner is not None:
        if __package__:from . import decoder_corpus_interruptions as interruptions
        else:import decoder_corpus_interruptions as interruptions
        version=10 if checkpoint_owner.get('checkpoint_origin')=='fresh_worker_training_progress' else 9 if checkpoint_owner.get('checkpoint_origin')=='fresh_worker_reference_progress' else 8 if checkpoint_owner.get('checkpoint_origin')=='fresh_worker_reference_midpoint' else 7 if checkpoint_owner.get('checkpoint_origin')=='fresh_worker_reference_start' else 6 if checkpoint_owner.get('checkpoint_origin')=='fresh_worker_training_start' else 5
        record.update(checkpoint_owner,format=f'almg-corpus-optimizer-run-v{version}',schema_version=version,status='interruption_checkpoint')
        record['workflow_measurements']={'measured':False,'isolated_trial_peak_measured':False,'scope':'durable_training_progress_snapshot_only' if version==10 else 'durable_reference_progress_snapshot_only' if version==9 else 'durable_reference_midpoint_snapshot_only' if version==8 else 'durable_reference_start_snapshot_only' if version==7 else 'durable_training_start_snapshot_only' if version==6 else 'durable_midpoint_snapshot_only'}
        record['limitations']='Durable saved training point only. Originating worker may still be active. After interruption, separate approval can restore this counter; later uncheckpointed work must be replayed. No completed comparison, isolated measurement or release claim. Physical power-loss recovery is unverified.'
        interruptions.validate(root,folder,record)
        interruptions.flush_files(folder)
    record['revision']=digest(record);temporary=folder/'.canceled.tmp'
    with temporary.open('w') as stream:
        json.dump(record,stream,allow_nan=False,indent=2)
        if checkpoint_owner is not None:stream.flush();os.fsync(stream.fileno())
    temporary.replace(folder/'record.json')
    if checkpoint_owner is not None:interruptions.flush_directories(folder)
    return read(root,folder,record)


def _state(folder,name,model,c,step):
    data=json.loads((folder/name).read_text());expected=set(model.parameters) if c['optimizer']=='adamw' and step else set()
    if type(data['step']) is not int or data['step']!=step:raise ValueError('Canceled corpus optimizer counter changed.')
    for kind in ('m','v'):
        if set(data[kind])!=expected:raise ValueError('Canceled corpus moments are missing.')
        for key,value in data[kind].items():
            array=np.asarray(value,dtype=np.float32)
            if array.shape!=model.parameters[key].shape or not np.isfinite(array).all() or (kind=='v' and np.any(array<0)):raise ValueError('Canceled corpus moments are invalid.')


def read(root,folder,record):
    training=_training();approved=record['review'];c=training.configuration(approved['config'],approved['config']['sequence_length']);step=record['completed_steps'];phase=record.get('cancellation_phase');midpoint=c['steps']//2
    expected={'trained-model.json','optimizer.json','tokenizer.json'}
    if phase=='checkpointed_training':expected|={'reference-model.json','reference-optimizer.json'}
    if record.get('checkpoint_restored_steps')==midpoint:expected|={f'step-{midpoint}/{name}' for name in ('model.json','optimizer.json','checkpoint.json')}
    checkpoint=record.get('format') in ('almg-corpus-optimizer-run-v5','almg-corpus-optimizer-run-v6','almg-corpus-optimizer-run-v7','almg-corpus-optimizer-run-v8','almg-corpus-optimizer-run-v9','almg-corpus-optimizer-run-v10')
    if checkpoint:
        if __package__:from . import decoder_corpus_interruptions
        else:import decoder_corpus_interruptions
        decoder_corpus_interruptions.validate(root,folder,record)
    if ((record.get('format'),record.get('schema_version'),record.get('status')) not in (('almg-corpus-optimizer-run-v4',4,'canceled'),('almg-corpus-optimizer-run-v5',5,'interruption_checkpoint'),('almg-corpus-optimizer-run-v6',6,'interruption_checkpoint'),('almg-corpus-optimizer-run-v7',7,'interruption_checkpoint'),('almg-corpus-optimizer-run-v8',8,'interruption_checkpoint'),('almg-corpus-optimizer-run-v9',9,'interruption_checkpoint'),('almg-corpus-optimizer-run-v10',10,'interruption_checkpoint')) or record.get('id')!=folder.name
            or phase not in ('reference_verification','checkpointed_training') or type(step) is not int or not 0<=step<c['steps']
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'}) or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
            or set(record['files'])!=expected or any((folder/name).stat().st_size>16*1024**2 or file_digest(folder/name)!=sha for name,sha in record['files'].items())
            or record['scheduler_completed_steps']!=step or record.get('reference_verified') is not False or record.get('release_approved') is not False
            or (not checkpoint and not requested(root,approved,record.get('request_id')))):raise ValueError('Canceled fresh corpus artifact or receipt binding changed.')
    corpus=training.inputs.read(root,approved['corpus_id'])
    if corpus['revision']!=approved['corpus_revision']:raise ValueError('Canceled corpus input snapshot changed.')
    model=training.PlannedDecoder.load(folder/'trained-model.json');_state(folder,'optimizer.json',model,c,step)
    if model.config!=approved['model_config'] or record['compute_precision']!=c['compute_precision'] or record['loss_scale']!=c['loss_scale'] or record['master_parameter_dtype']!='float32' or record['optimizer_state_dtype']!='float32':raise ValueError('Canceled corpus configuration changed.')
    if phase=='reference_verification':
        if record['reference_completed_steps']!=step or record['recorded_training_updates']!=0 or record['checkpoint_restored_steps']!=0:raise ValueError('Canceled reference counters changed.')
    else:
        if record['reference_completed_steps']!=c['steps'] or record['recorded_training_updates']!=step or record['checkpoint_restored_steps']!=(midpoint if step>=midpoint else 0):raise ValueError('Canceled training counters changed.')
        reference=training.PlannedDecoder.load(folder/'reference-model.json')
        if reference.config!=model.config:raise ValueError('Retained reference model configuration changed.')
        _state(folder,'reference-optimizer.json',reference,c,c['steps'])
        if step>=midpoint:training.optimizer.restore(folder/f'step-{midpoint}',c,approved['revision'])
    windows=json.loads((Path(root)/'decoder-corpus-inputs'/corpus['id']/'windows.json').read_text())['train']
    for logs,count in ((record['step_log'],step),(record['reference_step_log'],record['reference_completed_steps'])):
        if len(logs)!=count:raise ValueError('Canceled corpus phase log length changed.')
        for index,entry in enumerate(logs):
            indices,arrays=training.batch_arrays(windows,index,c['batch_size'])
            if entry['step']!=index+1 or entry['window_indices']!=indices or entry['target_tokens']!=int(arrays[2].sum()) or entry['learning_rate']!=training.optimizer.learning_rate(c,index):raise ValueError('Canceled corpus phase schedule changed.')
    tokenizer=training.Tokenizer.restore(json.loads((folder/'tokenizer.json').read_text()))
    if tokenizer.fingerprint()!=corpus['review']['tokenizer_sha256'] or training._generated(model,tokenizer)!=(record['generated_token_ids'],record['generated_text']):raise ValueError('Canceled corpus tokenizer/CPU generation changed.')
    if 'isolated_workflow_measurements' in record:
        if approved.get('execution_mode')!='fresh_process' or training.feedback.measurements(record) is None:raise ValueError('Canceled corpus measurements lack matching execution policy.')
    return record
