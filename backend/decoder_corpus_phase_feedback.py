"""Exact retained source/phase observations for bounded fresh-run resume reviews."""
import math
if __package__:
    from .run_manifest import digest
    from . import decoder_corpus_feedback as observations
else:
    from run_manifest import digest
    import decoder_corpus_feedback as observations


def feedback(records,current,phase):
    binding_key='reference_resume_from' if phase=='reference_resume' else 'training_resume_from'
    binding=current.get(binding_key)
    if phase not in ('reference_resume','training_resume') or not isinstance(binding,dict):raise ValueError('Choose an exact retained corpus resume phase.')
    keys=('format','schema_version','scope','source','reference_resume_from','training_resume_from','corpus_id','corpus_revision','config','model_config','runtime','implementation_sha256','execution_mode')
    samples=[];c=current['config'];carried=binding['completed_steps']
    for record in records:
        try:
            saved=record['review'];observed=observations.measurements(record)
            if (observed is None or observed.get('action')!=phase or record.get('status')!='completed'
                    or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                    or any(saved.get(key)!=current.get(key) for key in keys) or saved.get('execution_mode')!='fresh_process'
                    or record.get('training_approved') is not True or record.get('release_approved') is not False
                    or record.get('completed_steps')!=c['steps'] or record.get('scheduler_completed_steps')!=c['steps']
                    or record.get('checkpoint_restored_steps')!=c['steps']//2):continue
            if phase=='reference_resume':
                if record.get('reference_steps_carried')!=carried or record.get('reference_updates_executed')!=c['steps']-carried:continue
            elif (record.get('training_steps_carried')!=carried or record.get('training_updates_executed')!=c['steps']-carried
                  or record.get('reference_steps_carried')!=c['steps'] or record.get('reference_updates_executed')!=0):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'elapsed_seconds':observed['elapsed_seconds'],
                            'peak_rss_bytes':observed['isolated_process_peak_rss_bytes'],'peak_metal_bytes':observed['isolated_metal_peak_bytes']})
        except (ValueError,TypeError,KeyError,AttributeError):continue
    if not samples:return None,None
    times=[sample['elapsed_seconds'] for sample in samples];rss=max(sample['peak_rss_bytes'] for sample in samples);metal=max(sample['peak_metal_bytes'] for sample in samples)
    common={'format':'almg-corpus-phase-resume-feedback-v1','schema_version':1,'phase':phase,
            'sample_count':len(samples),'source_records':samples,'headroom_multiplier':1.25}
    memory={**common,'measured':True,'isolated_process_peak_rss_bytes':rss,'isolated_metal_peak_bytes':metal,
            'calculated_memory_floor_bytes':math.ceil((rss+metal)*1.25),
            'limitations':'Exact retained source/revision/phase/counter, corpus/config/runtime/producer only. RSS and Metal may overlap in unified memory; their sum plus 25% headroom is a conservative calculated floor. Never reduces existing reserves. Latest twenty verified corpus runs; incomplete/canceled samples excluded.'}
    work={**common,'measured':False,'estimated_seconds':max(times)*1.25,'observed_min_seconds':min(times),'observed_max_seconds':max(times),
          'limitations':'Heuristic exact phase-resume work estimate. Includes worker imports/admission/lineage checks, model loading, only the approved phase work, checkpoint saving/restore, evaluation and CPU inference. Reference resume completes remaining reference updates plus original recorded training; recorded-training resume reuses the complete reference. Excludes parent launch/admission and queue/approval waits. No total wall-time bound, confidence interval or larger-model prediction.'}
    return memory,work


def apply(root,initialized,corpus,result,phase):
    if __package__:from . import decoder_corpus_optimizer as training
    else:import decoder_corpus_optimizer as training
    memory,work=feedback(training.history(root,initialized,corpus),result,phase) if result['execution_mode']=='fresh_process' else (None,None)
    estimates=result['estimates'];estimates['isolated_phase_resume_memory']=memory;estimates['phase_resume_work_estimate']=work
    training.feedback.apply_memory_floor(estimates,memory)
    if not training.hardware._fits(result['hardware'],estimates) and not any('memory/disk' in reason for reason in result['blockers']):result['blockers'].append('Current memory/disk or Metal working-set recommendation does not cover measured phase-resume calibration reserves.')
    result['feasible']=not result['blockers']
