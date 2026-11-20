"""Fresh-worker feedback scoped to the exact corpus checkpoint/partial source."""
import math
if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


def measurements(record):
    value=record.get('isolated_workflow_measurements')
    if not isinstance(value,dict):return None
    if (value.get('format')!='almg-isolated-corpus-continuation-measurements-v1' or value.get('schema_version')!=1
            or value.get('scope')!='fresh_process_corpus_checkpoint_continuation'
            or value.get('action') not in ('continuation','partial_resume')
            or value.get('measured') is not True or value.get('isolated_trial_peak_measured') is not True
            or type(value.get('process_id')) is not int or value['process_id']<=0
            or type(value.get('elapsed_seconds')) not in (int,float) or not math.isfinite(value['elapsed_seconds']) or value['elapsed_seconds']<=0
            or type(value.get('isolated_process_peak_rss_bytes')) is not int or value['isolated_process_peak_rss_bytes']<=0
            or type(value.get('isolated_metal_peak_bytes')) is not int or value['isolated_metal_peak_bytes']<0):
        raise ValueError('Invalid isolated corpus continuation measurements.')
    expected='partial_resume' if record['review'].get('resume_from') is not None else 'continuation'
    if value['action']!=expected:raise ValueError('Corpus worker measurements belong to another continuation kind.')
    return value


def feedback(records,current):
    samples=[]
    keys=('source','resume_from','restore_step','corpus_id','corpus_revision','config','runtime','implementation_sha256','execution_mode')
    for record in records:
        try:
            observed=measurements(record);saved=record['review'];c=current['config']
            if (observed is None or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                    or record.get('status','completed')!='completed' or record.get('training_approved') is not True
                    or saved.get('execution_mode')!='fresh_process' or any(saved.get(key)!=current.get(key) for key in keys)
                    or record.get('restored_step')!=current['restore_step'] or record.get('completed_steps')!=c['steps']
                    or record.get('scheduler_completed_steps')!=c['steps']):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'elapsed_seconds':observed['elapsed_seconds'],
                            'peak_rss_bytes':observed['isolated_process_peak_rss_bytes'],'peak_metal_bytes':observed['isolated_metal_peak_bytes']})
        except (ValueError,TypeError,KeyError,AttributeError):continue
    if not samples:return None,None
    times=[sample['elapsed_seconds'] for sample in samples];rss=max(sample['peak_rss_bytes'] for sample in samples);metal=max(sample['peak_metal_bytes'] for sample in samples)
    memory={'measured':True,'sample_count':len(samples),'isolated_process_peak_rss_bytes':rss,'isolated_metal_peak_bytes':metal,
            'calculated_memory_floor_bytes':math.ceil((rss+metal)*1.25),'source_records':samples,'headroom_multiplier':1.25,
            'limitations':'RSS/Metal sum with 25% headroom is conservative because unified memory can overlap. Never reduces calculated reserves. Exact original checkpoint/retained-partial revision and restored step, corpus/config/runtime/producer only; canceled observations excluded.'}
    work={'measured':False,'sample_count':len(samples),'estimated_seconds':max(times)*1.25,'observed_min_seconds':min(times),'observed_max_seconds':max(times),
          'source_records':samples,'headroom_multiplier':1.25,
          'limitations':'Heuristic exact remaining-work estimate; includes worker imports/admission/lineage checks, restore, remaining updates, saved state and CPU inference. Excludes parent launch/admission and queue/approval waits. No uninterrupted training trajectory; not a total wall-time bound, larger-model prediction or confidence interval. Latest twenty verified records for this original run; canceled samples excluded.'}
    return memory,work
