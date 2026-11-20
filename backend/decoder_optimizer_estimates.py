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


def estimate(records,current):
    samples=[]
    for record in records:
        try:
            saved=record['review'];observed=record['workflow_measurements'];seconds=observed['elapsed_seconds'];steps=current['config']['steps']
            if (record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                or any(saved.get(key)!=current[key] for key in ('source','config','model_config','runtime','implementation_sha256'))
                or record.get('optimizer')!=current['config'] or record.get('training_approved') is not True
                or record.get('completed_steps')!=steps or record.get('scheduler_completed_steps')!=steps
                or record.get('checkpoint_restored_steps')!=steps//2
                or observed.get('format')!='almg-optimizer-workflow-measurements-v1' or observed.get('schema_version')!=1
                or observed.get('scope')!='bounded_optimizer_fixture_in_shared_backend' or observed.get('measured') is not True
                or type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0):continue
            samples.append({'record_id':record['id'],'record_revision':record['revision'],'measured_seconds':seconds})
        except (KeyError,TypeError,ValueError,AttributeError):continue
    if not samples:return None
    times=[sample['measured_seconds'] for sample in samples]
    return {'estimated_seconds':max(times)*1.25,'measured':False,'sample_count':len(samples),
        'observed_min_seconds':min(times),'observed_max_seconds':max(times),'source_records':samples,
        'method':'highest_compatible_completed_optimizer_work_time_with_25_percent_headroom','headroom_multiplier':1.25,
        'scope':'Exact initialization/configuration, Python/NumPy/MLX/Metal device/CPU topology and producer only; both reference and checkpointed trajectories plus checkpoint/inference work.',
        'limitations':'Heuristic work estimate, not an upper bound or confidence interval. Excludes queue, approval, admission and report publication. Shared load and sampling overhead affect timing; total wall time remains unknown. No memory reserve reduction. Only the latest twenty verified records for this initialization are considered.'}
