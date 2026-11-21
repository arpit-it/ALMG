"""Separate approval for continuing a retained, incomplete reference trajectory."""
import json
import numpy as np
if __package__:
    from . import decoder_corpus_optimizer as training
else:
    import decoder_corpus_optimizer as training


def snapshot(record):
    if ((record.get('format'),record.get('status')) not in (('almg-corpus-optimizer-run-v4','canceled'),('almg-corpus-optimizer-run-v7','interruption_checkpoint')) or record.get('cancellation_phase')!='reference_verification'):
        raise ValueError('Select retained reference verification or a durable reference-start checkpoint.')
    depth=record.get('reference_resume_depth',0)
    if type(depth) is not int or not 0<=depth<=16:raise ValueError('Invalid retained reference ancestry depth.')
    return {'record_id':record['id'],'record_revision':record['revision'],'files':record['files'],
            'phase':'reference_verification','completed_steps':record['completed_steps'],
            'lineage_depth':record.get('reference_resume_depth',0)}


def lineage(root,record,seen):
    binding=record['review'].get('reference_resume_from')
    if binding is None:return
    if not isinstance(binding,dict):raise ValueError('Invalid retained reference binding.')
    parent=training.read(root,binding.get('record_id'),seen)
    if (snapshot(parent)!=binding or record.get('reference_resume_depth')!=binding['lineage_depth']+1
            or not 1<=record['reference_resume_depth']<=16
            or any(record['review'].get(key)!=parent['review'].get(key) for key in ('source','corpus_id','corpus_revision','config','model_config'))):
        raise ValueError('Retained reference ancestry or configuration changed.')
    expected=record['completed_steps'] if record.get('cancellation_phase')=='reference_verification' else record['review']['config']['steps']
    if (record.get('reference_updates_executed')!=expected-binding['completed_steps']
            or record.get('reference_steps_carried')!=binding['completed_steps']):
        raise ValueError('Retained reference executed/carried counters changed.')
    logs=record.get('reference_step_log',[])
    if len(logs)!=expected or logs[:binding['completed_steps']]!=parent['reference_step_log']:raise ValueError('Carried reference log changed.')
    c=record['review']['config']
    corpus=training.inputs.read(root,record['review']['corpus_id'])
    windows=json.loads((training.Path(root)/'decoder-corpus-inputs'/corpus['id']/'windows.json').read_text())['train']
    for index,entry in enumerate(logs):
        indices,arrays=training.batch_arrays(windows,index,c['batch_size'])
        if entry['step']!=index+1 or entry['window_indices']!=indices or entry['target_tokens']!=int(arrays[2].sum()) or entry['learning_rate']!=training.optimizer.learning_rate(c,index):raise ValueError('Resumed reference schedule changed.')


def source(root,identifier):
    parent=training.read(root,identifier);binding=snapshot(parent)
    if parent.get('status')=='interruption_checkpoint':
        if __package__:from . import decoder_corpus_interruptions
        else:import decoder_corpus_interruptions
        decoder_corpus_interruptions.require_recoverable(root,parent)
    if binding['lineage_depth']>=16:raise ValueError('Reference resume supports at most sixteen ancestors.')
    origin=parent['review']['source']
    initialized=training.hardware.initializations.read(root,origin['plan_id'],origin['initialization_id'])
    corpus=training.inputs.read(root,parent['review']['corpus_id'])
    return parent,initialized,corpus


def review(root,identifier,execution_mode='fresh_process'):
    parent,initialized,corpus=source(root,identifier)
    result=training.review(root,initialized,corpus,parent['review']['config'],execution_mode)
    result.update(format='almg-corpus-reference-resume-review-v1',schema_version=1,
                  reference_resume_from=snapshot(parent),training_approved=False,
                  scope='finish_retained_reference_then_execute_original_checkpointed_training')
    result['estimates']={**result['estimates'],'reference_optimizer_updates':result['config']['steps']-parent['completed_steps'],
                         'recorded_training_optimizer_updates':result['config']['steps'],
                         'corpus_work_estimate':None,'isolated_corpus_memory':None}
    if __package__:from . import decoder_corpus_phase_feedback
    else:import decoder_corpus_phase_feedback
    decoder_corpus_phase_feedback.apply(root,initialized,corpus,result,'reference_resume')
    result['revision']=training.digest({k:v for k,v in result.items() if k!='revision'})
    return result


def state(root,parent):
    folder=training._folder(root,parent['id']);model=training.PlannedDecoder.load(folder/'trained-model.json')
    value=json.loads((folder/'optimizer.json').read_text())
    return model.parameters,{'step':value['step'],**{kind:{name:np.asarray(array,dtype=np.float32) for name,array in value[kind].items()} for kind in ('m','v')}}


def metadata(approved,reference_steps):
    binding=approved.get('reference_resume_from')
    if binding is None:return {}
    return {'reference_resume_depth':binding['lineage_depth']+1,'reference_steps_carried':binding['completed_steps'],
            'reference_updates_executed':reference_steps-binding['completed_steps']}


def run(root,identifier,confirmed,approved,request_id=None,execution_mode='fresh_process'):
    _,initialized,corpus=source(root,identifier)
    return training.run(root,confirmed,initialized,corpus,approved['config'],approved,execution_mode,request_id,identifier)
