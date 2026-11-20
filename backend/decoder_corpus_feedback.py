"""Exact-corpus fresh-worker observations; calibrated reserves never decrease."""
import math
if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


def measurements(record):
    value=record.get('isolated_workflow_measurements')
    if not isinstance(value,dict):return None
    if (value.get('format')!='almg-isolated-corpus-optimizer-measurements-v1' or value.get('schema_version')!=1
            or value.get('scope')!='fresh_process_reviewed_corpus_optimizer' or value.get('measured') is not True
            or value.get('isolated_trial_peak_measured') is not True
            or type(value.get('process_id')) is not int or value['process_id']<=0
            or type(value.get('elapsed_seconds')) not in (float,int) or not math.isfinite(value['elapsed_seconds']) or value['elapsed_seconds']<=0
            or any(type(value.get(key)) is not int or value[key]<=0 for key in ('isolated_process_peak_rss_bytes','isolated_metal_peak_bytes'))):
        raise ValueError('Invalid isolated corpus optimizer measurements.')
    return value


def feedback(records,current):
    samples=[]
    for record in records:
        try:
            saved=record['review'];c=current['config'];observed=measurements(record)
            keys=('source','corpus_id','corpus_revision','config','model_config','runtime','implementation_sha256','execution_mode')
            if (observed is None or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                    or any(saved.get(key)!=current.get(key) for key in keys) or saved.get('execution_mode')!='fresh_process'
                    or record.get('training_approved') is not True or record.get('completed_steps')!=c['steps']
                    or record.get('scheduler_completed_steps')!=c['steps'] or record.get('checkpoint_restored_steps')!=c['steps']//2):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],
                'elapsed_seconds':observed['elapsed_seconds'],'peak_rss_bytes':observed['isolated_process_peak_rss_bytes'],
                'peak_metal_bytes':observed['isolated_metal_peak_bytes']})
        except (ValueError,TypeError,KeyError,AttributeError):continue
    if not samples:return None,None
    seconds=[sample['elapsed_seconds'] for sample in samples]
    rss=max(sample['peak_rss_bytes'] for sample in samples);metal=max(sample['peak_metal_bytes'] for sample in samples)
    work={'measured':False,'sample_count':len(samples),'estimated_seconds':max(seconds)*1.25,
          'observed_min_seconds':min(seconds),'observed_max_seconds':max(seconds),'headroom_multiplier':1.25,'source_records':samples,
          'limitations':'Heuristic exact-corpus/configuration/runtime/producer work estimate, not a bound or confidence interval. Includes worker imports/admission, both training trajectories, checkpoints and CPU inference; excludes parent admission/process launch, queue/approval waits and final measurement publication. No large-model or total wall-time prediction.'}
    memory={'measured':True,'sample_count':len(samples),'isolated_process_peak_rss_bytes':rss,'isolated_metal_peak_bytes':metal,
            'calculated_memory_floor_bytes':math.ceil((rss+metal)*1.25),'headroom_multiplier':1.25,'source_records':samples,
            'limitations':'Calculated floor sums fresh-process RSS and Metal peaks with 25% headroom; unified-memory overlap makes this conservative. Never reduces calculated reserves. Exact corpus/config/runtime/producer only, latest twenty verified runs for this corpus; changing host load can still exhaust resources.'}
    return memory,work
