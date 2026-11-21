"""Approved continuation of a canceled fresh run's recorded training phase."""
import json
import numpy as np
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_reference_resume as reference_resume
else:
    import decoder_corpus_optimizer as training, decoder_corpus_reference_resume as reference_resume


def snapshot(record):
    if ((record.get('format'),record.get('status')) not in (('almg-corpus-optimizer-run-v4','canceled'),('almg-corpus-optimizer-run-v5','interruption_checkpoint'),('almg-corpus-optimizer-run-v6','interruption_checkpoint'),('almg-corpus-optimizer-run-v10','interruption_checkpoint'),('almg-corpus-optimizer-run-v11','interruption_checkpoint'),('almg-corpus-optimizer-run-v13','interruption_checkpoint')) or record.get('cancellation_phase')!='checkpointed_training'):
        raise ValueError('Select retained recorded training or a durable interrupted training checkpoint.')
    depth=record.get('training_resume_depth',record.get('reference_resume_depth',0))
    if type(depth) is not int or not 0<=depth<=16:raise ValueError('Invalid recorded-training ancestry depth.')
    return {'record_id':record['id'],'record_revision':record['revision'],'files':record['files'],
            'phase':'checkpointed_training','completed_steps':record['completed_steps'],'lineage_depth':depth}


def source(root,identifier):
    parent=training.read(root,identifier);binding=snapshot(parent)
    if parent.get('status')=='interruption_checkpoint':
        if __package__:from . import decoder_corpus_interruptions
        else:import decoder_corpus_interruptions
        decoder_corpus_interruptions.require_recoverable(root,parent)
    if binding['lineage_depth']>=16:raise ValueError('Recorded training resume supports at most sixteen ancestors.')
    origin=parent['review']['source']
    initialized=training.hardware.initializations.read(root,origin['plan_id'],origin['initialization_id'])
    corpus=training.inputs.read(root,parent['review']['corpus_id'])
    return parent,initialized,corpus


def review(root,identifier,execution_mode='fresh_process'):
    parent,initialized,corpus=source(root,identifier)
    result=training.review(root,initialized,corpus,parent['review']['config'],execution_mode)
    result.update(format='almg-corpus-training-resume-review-v1',schema_version=1,
                  training_resume_from=snapshot(parent),training_approved=False,
                  scope='reuse_completed_reference_and_finish_retained_recorded_training')
    result['estimates']={**result['estimates'],'reference_optimizer_updates':0,
                         'recorded_training_optimizer_updates':result['config']['steps']-parent['completed_steps'],
                         'corpus_work_estimate':None,'isolated_corpus_memory':None}
    if __package__:from . import decoder_corpus_phase_feedback
    else:import decoder_corpus_phase_feedback
    decoder_corpus_phase_feedback.apply(root,initialized,corpus,result,'training_resume')
    result['revision']=training.digest({k:v for k,v in result.items() if k!='revision'})
    return result


def reference(root,parent):
    folder=training._folder(root,parent['id']);model=training.PlannedDecoder.load(folder/'reference-model.json')
    return model.parameters,training.run_cancellation._state(folder,'reference-optimizer.json',model,parent['review']['config'],parent['review']['config']['steps'])


def metadata(approved,step):
    binding=approved.get('training_resume_from')
    if binding is None:return {}
    return {'training_resume_depth':binding['lineage_depth']+1,'training_steps_carried':binding['completed_steps'],
            'training_updates_executed':step-binding['completed_steps'],
            'reference_steps_carried':approved['config']['steps'],'reference_updates_executed':0}


def lineage(root,record,seen):
    binding=record['review'].get('training_resume_from')
    if binding is None:return
    if not isinstance(binding,dict) or record['review'].get('reference_resume_from') is not None:raise ValueError('Invalid recorded-training resume binding.')
    parent=training.read(root,binding.get('record_id'),seen)
    if (snapshot(parent)!=binding or record.get('training_resume_depth')!=binding['lineage_depth']+1
            or not 1<=record['training_resume_depth']<=16
            or any(record['review'].get(key)!=parent['review'].get(key) for key in ('source','corpus_id','corpus_revision','config','model_config'))):
        raise ValueError('Recorded-training ancestry or configuration changed.')
    c=record['review']['config']
    if (record.get('training_updates_executed')!=record['completed_steps']-binding['completed_steps']
            or record.get('training_steps_carried')!=binding['completed_steps']
            or record.get('reference_updates_executed')!=0 or record.get('reference_steps_carried')!=c['steps']
            or record.get('reference_step_log')!=parent['reference_step_log']
            or record.get('step_log',[])[:binding['completed_steps']]!=parent['step_log']):
        raise ValueError('Carried reference/training state or executed counters changed.')
    if record.get('status') in ('canceled','interruption_checkpoint') and any(record['files'].get(name)!=parent['files'][name] for name in ('reference-model.json','reference-optimizer.json')):
        raise ValueError('Retained completed reference artifacts changed.')
    midpoint=c['steps']//2
    if binding['completed_steps']>=midpoint:
        for name in ('model.json','optimizer.json'):
            if record['files'].get(f'step-{midpoint}/{name}')!=parent['files'][f'step-{midpoint}/{name}']:raise ValueError('Retained midpoint state changed during resume.')


def run(root,identifier,confirmed,approved,request_id=None,execution_mode='fresh_process'):
    _,initialized,corpus=source(root,identifier)
    return training.run(root,confirmed,initialized,corpus,approved['config'],approved,execution_mode,request_id,training_resume_id=identifier)
