"""Optional saved-trial worker timing; never changes model/checkpoint execution."""
from datetime import datetime,timezone
from pathlib import Path
import math
import os
import platform
from time import perf_counter
import uuid
if __package__:
    from . import decoder_trials as trials,decoder_architecture_feasibility as architecture
    from .run_manifest import digest,file_digest
else:
    import decoder_trials as trials,decoder_architecture_feasibility as architecture
    from run_manifest import digest,file_digest


def implementation():
    return digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_trial_measurements.py','decoder_trial_feasibility.py','decoder_trials.py','decoder_training.py','decoder_dataset_training.py','decoder_checkpoint.py','decoder_bundle.py','decoder_recipe.py')})


def runtime(hardware):
    return {**{key:hardware.get(key) for key in ('system','machine','mlx_version','metal_device')},
            'python':platform.python_version(),'numpy':trials.decoder_bundle.version('numpy'),'logical_cpu_count':os.cpu_count()}


def _save_observation(root,trial_id,context,seconds):
    if not math.isfinite(seconds) or seconds<=0:return
    with trials._LOCK:
        record=trials.read(root,trial_id)
        if record['approval']['id']!=context['approval_id'] or digest(record['specification'])!=context['specification_sha256']:return
        observation={'format':'almg-saved-decoder-worker-time-v1','schema_version':1,'id':uuid.uuid4().hex,
            'created_at':datetime.now(timezone.utc).isoformat(),'trial_id':trial_id,**context,
            'elapsed_seconds':seconds,'outcome':record['status'],'measured':True,'peak_memory_measured':False,
            'scope':'saved_trial_worker_function_in_shared_backend',
            'limitations':'Elapsed worker work includes model loading, training, evaluation, checkpoints, bundle persistence and engine state writes. Excludes queue/approval/idle waits, the measurement hardware probe and this observation publication. Shared process/load; no isolated peak memory or total wall-time prediction.'}
        observation['revision']=digest(observation)
        record['worker_measurements']=[*record.get('worker_measurements',[]),observation];trials.write(root,record)


def execute(function,root,trial_id):
    context=None
    try:
        if __package__:from .decoder_trial_feasibility import _checkpoint
        else:from decoder_trial_feasibility import _checkpoint
        with trials._LOCK:record=trials.read(root,trial_id)
        context={'approval_id':record['approval']['id'],'specification_sha256':digest(record['specification']),
                 'started_checkpoint':_checkpoint(root,trial_id),'runtime':runtime(architecture.hardware(root)),
                 'implementation_sha256':implementation()}
    except Exception:
        # Optional evidence must not prevent the existing engine's recovery/error handling.
        context=None
    started=perf_counter()
    try:return function(root,trial_id)
    finally:
        seconds=perf_counter()-started
        if context is not None:
            try:_save_observation(root,trial_id,context,seconds)
            except Exception:pass  # Preserve the engine's result and all training artifacts if evidence cannot publish.


def estimate(root,specification_sha256,hardware,checkpoint=None):
    checkpoint={'completed_steps':0,'files':{}} if checkpoint is None else checkpoint
    expected_runtime=runtime(hardware);producer=implementation();samples=[]
    for record in trials.list_trials(root,limit=200):
        if record['status']!='complete' or digest(record.get('specification'))!=specification_sha256:continue
        observations=record.get('worker_measurements',[])
        if not isinstance(observations,list):continue
        for observation in observations:
            try:
                seconds=observation['elapsed_seconds']
                if (observation.get('format')!='almg-saved-decoder-worker-time-v1' or observation.get('schema_version')!=1
                    or observation.get('revision')!=digest({k:v for k,v in observation.items() if k!='revision'})
                    or observation.get('trial_id')!=record['id'] or observation.get('approval_id')!=(record.get('approval') or {}).get('id')
                    or observation.get('specification_sha256')!=specification_sha256 or observation.get('runtime')!=expected_runtime
                    or observation.get('implementation_sha256')!=producer or observation.get('started_checkpoint')!=checkpoint
                    or observation.get('scope')!='saved_trial_worker_function_in_shared_backend' or observation.get('outcome')!='complete'
                    or observation.get('measured') is not True or type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0):continue
                samples.append({'trial_id':record['id'],'measurement_id':observation['id'],'revision':observation['revision'],'measured_seconds':seconds})
            except (KeyError,TypeError,ValueError,AttributeError):continue
    if not samples:return None
    times=[sample['measured_seconds'] for sample in samples]
    return {'estimated_seconds':max(times)*1.25,'measured':False,'sample_count':len(samples),
            'observed_min_seconds':min(times),'observed_max_seconds':max(times),'source_measurements':samples,
            'method':'highest_compatible_completed_worker_time_with_25_percent_headroom','headroom_multiplier':1.25,
            'scope':'Same specification/data, runtime/CPU topology/Metal device, implementation and input checkpoint only; includes checkpoint/bundle persistence.',
            'limitations':'Heuristic worker-work estimate, not an upper bound or confidence interval. Queue, user approval, idle/AC waits and timing-publication work are excluded. Shared machine load may change; total wall time remains unknown. At most the latest 200 trial records are considered.'}
