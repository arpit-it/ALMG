"""Conservative work-time hints from exact compatible completed optimizer fixtures."""
import math
import os
import platform
import numpy as np
if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


def runtime(hardware):
    return {**{key:hardware.get(key) for key in ('system','machine','mlx_version','metal_device')},
        'python':platform.python_version(),'numpy':np.__version__,'logical_cpu_count':os.cpu_count()}


def compatible(record,current):
    saved=record['review'];steps=current['config']['steps']
    return (record.get('revision')==digest({k:v for k,v in record.items() if k!='revision'})
        and all(saved.get(key)==current[key] for key in ('source','config','model_config','runtime','implementation_sha256'))
        and record.get('optimizer')==current['config'] and record.get('training_approved') is True
        and record.get('completed_steps')==steps and record.get('scheduler_completed_steps')==steps
        and record.get('checkpoint_restored_steps')==steps//2)


def estimate(records,current):
    samples=[]
    for record in records:
        try:
            isolated='isolated_workflow_measurements' in record
            observed=record['isolated_workflow_measurements'] if isolated else record['workflow_measurements'];seconds=observed['elapsed_seconds']
            expected_format='almg-isolated-optimizer-measurements-v1' if isolated else 'almg-optimizer-workflow-measurements-v1'
            expected_scope='fresh_process_bounded_optimizer_fixture' if isolated else 'bounded_optimizer_fixture_in_shared_backend'
            if (not compatible(record,current) or observed.get('format')!=expected_format or observed.get('schema_version')!=1
                or observed.get('scope')!=expected_scope or observed.get('measured') is not True
                or (isolated and observed.get('isolated_trial_peak_measured') is not True)
                or type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'measured_seconds':seconds})
        except (KeyError,TypeError,ValueError,AttributeError):continue
    if not samples:return None
    times=[sample['measured_seconds'] for sample in samples]
    return {'estimated_seconds':max(times)*1.25,'measured':False,'sample_count':len(samples),
        'observed_min_seconds':min(times),'observed_max_seconds':max(times),'source_records':samples,
        'method':'highest_compatible_completed_optimizer_work_time_with_25_percent_headroom','headroom_multiplier':1.25,
        'scope':'Exact initialization/configuration, Python/NumPy/MLX/Metal device/CPU topology and producer only; both reference and checkpointed trajectories plus checkpoint/inference work; fresh-worker observations include bootstrap/imports.',
        'limitations':'Heuristic work estimate, not an upper bound or confidence interval. Excludes queue/approval waits and final measurement publication. Fresh-worker samples include internal admission but exclude parent admission/process launch; shared-backend samples exclude admission. Shared load and sampling overhead affect timing; total wall time remains unknown. No memory reserve reduction. Only the latest twenty verified records for this initialization are considered.'}


def memory_calibration(records,current):
    samples=[]
    for record in records:
        try:
            observed=record['isolated_workflow_measurements'];cpu=observed['isolated_process_peak_rss_bytes'];gpu=observed['isolated_metal_peak_bytes']
            if (not compatible(record,current) or observed.get('format')!='almg-isolated-optimizer-measurements-v1' or observed.get('schema_version')!=1
                or observed.get('scope')!='fresh_process_bounded_optimizer_fixture' or observed.get('measured') is not True
                or observed.get('isolated_trial_peak_measured') is not True or type(cpu) is not int or cpu<=0 or type(gpu) is not int or gpu<=0):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'peak_rss_bytes':cpu,'peak_metal_bytes':gpu})
        except (KeyError,TypeError,ValueError,AttributeError):continue
    if not samples:return None
    cpu=max(sample['peak_rss_bytes'] for sample in samples);gpu=max(sample['peak_metal_bytes'] for sample in samples)
    return {'measured':True,'sample_count':len(samples),'isolated_process_peak_rss_bytes':cpu,'isolated_metal_peak_bytes':gpu,
        'calculated_memory_floor_bytes':math.ceil((cpu+gpu)*1.25),'headroom_multiplier':1.25,'source_records':samples,
        'limitations':'Calculated floor sums fresh-process RSS and Metal peaks with 25% headroom; unified memory may overlap, so the sum is conservative. Never reduces calculated admission reserves. Same initialization/config/runtime/producer only; not a guarantee against changing host load or exhaustion.'}
