"""Feedback from exact compatible isolated checkpoint-continuation observations."""
import math
if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


def feedback(records,current):
    samples=[]
    for record in records:
        try:
            saved=record['review'];observed=record['isolated_workflow_measurements'];seconds=observed['elapsed_seconds'];cpu=observed['isolated_process_peak_rss_bytes'];gpu=observed['isolated_metal_peak_bytes']
            if ((record.get('format'),record.get('schema_version')) not in (('almg-optimizer-continuation-v1',1),('almg-optimizer-continuation-v2',2),('almg-optimizer-continuation-v3',3)) or record.get('status','completed')!='completed'
                or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                or any(saved.get(key)!=current[key] for key in ('source','config','runtime','implementation_sha256'))
                or record.get('training_approved') is not True or record.get('source_modified') is not False
                or saved.get('resume_from')!=current.get('resume_from') or record.get('restored_steps')!=current.get('restore_step',current['source']['checkpoint_step']) or record.get('completed_steps')!=current['config']['steps']
                or record.get('scheduler_completed_steps')!=current['config']['steps']
                or observed.get('format')!='almg-isolated-optimizer-continuation-measurements-v1' or observed.get('schema_version')!=1
                or observed.get('scope')!='fresh_process_optimizer_checkpoint_continuation' or observed.get('measured') is not True or observed.get('isolated_trial_peak_measured') is not True
                or type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0
                or type(cpu) is not int or cpu<=0 or type(gpu) is not int or gpu<=0):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'measured_seconds':seconds,'peak_rss_bytes':cpu,'peak_metal_bytes':gpu})
        except (KeyError,TypeError,ValueError,AttributeError):continue
    if not samples:return None,None
    cpu=max(sample['peak_rss_bytes'] for sample in samples);gpu=max(sample['peak_metal_bytes'] for sample in samples);seconds=[sample['measured_seconds'] for sample in samples]
    memory={'measured':True,'sample_count':len(samples),'isolated_process_peak_rss_bytes':cpu,'isolated_metal_peak_bytes':gpu,
        'calculated_memory_floor_bytes':math.ceil((cpu+gpu)*1.25),'headroom_multiplier':1.25,'source_records':samples,
        'limitations':'Fresh continuation worker/runtime peaks only. RSS and Metal can overlap in unified memory; summing them with 25% headroom is conservative and never reduces the preexisting admission reserve.'}
    work={'measured':False,'sample_count':len(samples),'estimated_seconds':max(seconds)*1.25,'headroom_multiplier':1.25,
        'observed_min_seconds':min(seconds),'observed_max_seconds':max(seconds),'source_records':samples,
        'scope':'Exact parent/checkpoint hashes, original configuration, runtime and continuation producer; remaining updates only, including bootstrap/imports, internal admission, checkpoint restoration and CPU inference.',
        'limitations':'Heuristic continuation-work estimate, not total wall time or a guarantee. Excludes process launch, parent admission, queue/approval waits and final publication. Shared host load may vary. Only the latest twenty verified continuations for this source are considered.'}
    return memory,work
