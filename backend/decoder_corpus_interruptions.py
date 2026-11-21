"""Immutable, flushed reference-start, training-start and midpoint snapshots for interrupted fresh corpus workers."""
import os
from pathlib import Path
import shutil
import uuid
if __package__:
    from . import decoder_corpus_optimizer as training
else:
    import decoder_corpus_optimizer as training
DIRECTORY='decoder-corpus-interruption-checkpoints'


def validate(root,folder,record):
    c=record['review']['config']
    version=record.get('schema_version');origin={5:'fresh_worker_midpoint',6:'fresh_worker_training_start',7:'fresh_worker_reference_start'}.get(version)
    step=c['steps']//2 if version==5 else 0
    phase='reference_verification' if version==7 else 'checkpointed_training'
    if (type(version) is not int or folder.parent!=Path(root)/DIRECTORY or (record.get('format'),version) not in (('almg-corpus-optimizer-run-v5',5),('almg-corpus-optimizer-run-v6',6),('almg-corpus-optimizer-run-v7',7)) or record.get('status')!='interruption_checkpoint'
            or record.get('checkpoint_origin')!=origin or record.get('cancellation_phase')!=phase
            or record.get('completed_steps')!=step or record['review'].get('execution_mode')!='fresh_process'
            or record['review'].get('reference_resume_from') is not None or record['review'].get('training_resume_from') is not None
            or type(record.get('owner_process_id')) is not int or record['owner_process_id']<=0
            or type(record.get('owner_parent_process_id')) is not int or record['owner_parent_process_id']<=0):
        raise ValueError('Invalid durable fresh-worker training checkpoint.')
    training.run_cancellation.validate(record.get('original_run_id'))
    if record['original_run_id']==record['id']:raise ValueError('Checkpoint and originating run must have different identities.')


def recoverable(root,record):
    if (Path(root)/'decoder-corpus-optimizer-runs'/record['original_run_id']/'record.json').exists():return False
    if os.name!='posix':return False
    try:os.kill(record['owner_process_id'],0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False


def require_recoverable(root,record):
    if not recoverable(root,record):raise ValueError('The originating worker is still active or already published a terminal result. Reopen its saved result instead.')


def flush_files(folder):
    for path in folder.rglob('*'):
        if path.is_file():
            with path.open('rb+') as stream:stream.flush();os.fsync(stream.fileno())


def flush_directories(folder):
    for path in (folder,folder.parent,folder.parent.parent):
        descriptor=os.open(path,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)


class _CheckpointObservation:
    def finish(self):return {'measured':False,'isolated_trial_peak_measured':False}


def publish(root,original_folder,initialized,corpus,approved,current,model,tokenizer,windows,initial,values,state,reference,reference_state,reference_log,first,token,phase='checkpointed_training'):
    identifier=uuid.uuid4().hex;folder=Path(root)/DIRECTORY/identifier;folder.mkdir(parents=True)
    midpoint=current['config']['steps']//2
    origin='fresh_worker_reference_start' if phase=='reference_verification' else 'fresh_worker_training_start' if state['step']==0 else 'fresh_worker_midpoint'
    if phase=='checkpointed_training' and state['step']!=0:shutil.copytree(original_folder/f'step-{midpoint}',folder/f'step-{midpoint}')
    retained=training.PlannedDecoder(model.config);retained.parameters=values
    event=training.run_cancellation.Stopped(values,state,[],phase)
    return training.run_cancellation.save(root,folder,identifier,initialized,corpus,approved,current,retained,tokenizer,windows,initial,event,reference,reference_state,reference_log,first,_CheckpointObservation(),token,
        checkpoint_owner={'checkpoint_origin':origin,'original_run_id':original_folder.name,'owner_process_id':os.getpid(),'owner_parent_process_id':os.getppid()})


def history(root,initialized,corpus):
    saved,source,_,_,_=training._source(root,initialized,corpus)
    records=[]
    for path in (Path(root)/DIRECTORY).glob('*/record.json'):
        record=training.read(root,path.parent.name)
        validate(root,path.parent,record)
        if (record['review']['corpus_id']==saved['id'] and record['review']['source']['initialization_id']==source['id'] and recoverable(root,record)):records.append(record)
    return latest(records)[-20:]


def latest(records):
    selected={}
    for record in records:
        previous=selected.get(record['original_run_id'])
        if previous is not None and (previous['review']['revision']!=record['review']['revision'] or previous['owner_process_id']!=record['owner_process_id']):raise ValueError('Conflicting checkpoint origin or approval binding.')
        if previous is None or progress(record)>progress(previous):selected[record['original_run_id']]=record
    return sorted(selected.values(),key=lambda record:record['created_at'])


def progress(record):
    return (record.get('cancellation_phase')=='checkpointed_training',record['completed_steps'],record['created_at'],record['id'])
