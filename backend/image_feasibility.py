"""Read-only CPU admission for the existing experimental 48-pixel image recipes."""
from copy import deepcopy
import json
import math
from importlib.metadata import version
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import warnings
if __package__:
    from . import image_recipe,recipe_contracts,training_resources
    from .run_manifest import digest,file_digest
else:
    import image_recipe,recipe_contracts,training_resources
    from run_manifest import digest,file_digest


def _calibrate(root, job, rows, settings, hardware, estimates):
    # Local import avoids a module cycle: trials use fresh feasibility admission.
    if __package__:
        from . import image_resource_trials
    else:
        import image_resource_trials
    producer = digest({name: file_digest(Path(__file__).with_name(name)) for name in
                       ('image_resource_trials.py', 'image_trial_worker.py', 'image_recipe.py', 'studio.py', 'recipe_contracts.py')})
    runtime = {'python': platform.python_version(), 'system': platform.system(),
               'machine': platform.machine(), 'numpy': version('numpy'), 'pillow': version('Pillow')}
    compatible = []
    for record in image_resource_trials.read(root, job['id'])['records']:
        observed = record.get('measurements', {})
        admission = record.get('admission', {})
        peak = observed.get('process_peak_rss_bytes')
        seconds = observed.get('fit_and_validation_seconds')
        if (record.get('dataset_sha256') != digest(rows) or record.get('settings') != settings
                or record.get('implementation_sha256') != producer
                or admission.get('implementation_sha256') != file_digest(Path(__file__))
                or record.get('mode') != job.get('mode')
                or record.get('variant') != recipe_contracts.execution_variant('text_to_image', job.get('mode'))
                or any(admission.get('hardware', {}).get(key) != hardware.get(key)
                       for key in ('system', 'machine', 'logical_cpu_count', 'training_device'))
                or observed.get('runtime') != runtime or observed.get('isolated_process') is not True
                or observed.get('weights_retained') is not False or observed.get('training_device') != 'CPU'
                or type(peak) is not int or peak <= 0 or type(seconds) not in (int, float)
                or not math.isfinite(seconds) or seconds <= 0):
            continue
        compatible.append(record)
    if not compatible:
        return None
    peak = max(record['measurements']['process_peak_rss_bytes'] for record in compatible)
    seconds = max(record['measurements']['fit_and_validation_seconds'] for record in compatible)
    estimates['required_available_memory_bytes'] = max(estimates['required_available_memory_bytes'], math.ceil(peak * 1.25))
    times = [record['measurements']['fit_and_validation_seconds'] for record in compatible]
    estimates['fit_work_estimate'] = {
        'estimated_seconds': seconds * 1.25, 'measured': False, 'sample_count': len(times),
        'observed_min_seconds': min(times), 'observed_max_seconds': seconds,
        'headroom_multiplier': 1.25, 'method': 'maximum_compatible_discarded_fit_with_25_percent_headroom',
        'trial_ids': [record['id'] for record in compatible],
        'scope': 'Prepared-file load, validation and fresh image fitting/evaluation on the same dataset/settings/runtime/CPU topology/implementation only.',
        'excludes': ['interpreter_and_import_startup', 'idle_or_power_waits', 'qwen_repair', 'checkpoint_and_candidate_persistence', 'export'],
        'limitations': 'Heuristic work estimate, not a confidence interval or upper bound. Shared CPU load may change. Does not predict total training wall time, checkpoint resume, larger datasets or other recipes.'}

    return {'trial_ids': [record['id'] for record in compatible], 'measured_process_peak_rss_bytes': peak,
            'memory_reserve_multiplier': 1.25, 'measured_fit_and_validation_seconds': seconds,
            'scope': 'Same prepared dataset/settings, CPU topology, runtime and implementation only. Highest observed discarded fit; not a full training duration or exhaustion guarantee. Memory reserves only increase; disk remains calculated. Repair, idle waits, imports and candidate persistence are excluded from measured time.'}


def review(root,job,rows,parameters):
    if job.get('recipe')!='text_to_image':raise ValueError('Choose the CPU image recipe.')
    settings=recipe_contracts.training_parameters('text_to_image',parameters,job.get('recipe_contract'))
    # Resource dimensions are meaningful only for the exact prepared-image contract.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',image_recipe.Image.DecompressionBombWarning)
            recipe_contracts.validate_dataset('text_to_image',job.get('mode'),rows)
    except (image_recipe.Image.DecompressionBombWarning,image_recipe.Image.DecompressionBombError) as error:
        raise ValueError('A valid prepared 48x48 RGB PNG is required; oversized image headers are not supported.') from error
    variant=recipe_contracts.execution_variant('text_to_image',job.get('mode'));encoded=len(json.dumps(rows,ensure_ascii=False).encode('utf-8'))
    count=sum(row.get('split')=='train' for row in rows);pixels=image_recipe.SIZE**2
    if variant=='local shapes':
        coefficients=len(image_recipe.SHAPES)*len(image_recipe.POSITIONS)*pixels+len(image_recipe.COLORS)*3
        buffers=count*pixels*8+coefficients*8*4;gram=0
    else:
        vocabulary=min(256,len(set(re.findall(r'[a-z0-9]+',' '.join(row['text'] for row in rows if row.get('split')=='train').lower()))))+1
        coefficients=vocabulary*pixels*3;gram=count*count*8
        buffers=gram*8+count*pixels*3*8*4+coefficients*8*4+count*vocabulary*8*4
    estimates={'dataset_encoded_bytes':encoded,'training_rows':count,'model_scalar_count':coefficients,
               'model_float64_layout_bytes':coefficients*8,'gram_matrix_layout_bytes':gram,'fitting_buffer_budget_bytes':buffers,
               'required_available_memory_bytes':256*1024**2+encoded*8+buffers,
               'required_free_disk_bytes':64*1024**2+encoded*4+coefficients*32,
               'measured':False,'duration_estimate_seconds':None,'fit_work_estimate':None,
               'assumptions':'Existing CPU NumPy/Pillow 48x48 recipe only. Local shapes estimate mask/palette means; caption ridge estimates dense target, Gram, solver and coefficient copies. JSON/model overhead is budgeted, not measured. Not diffusion or neural image training; runtime exhaustion remains possible.'}
    info={'system':platform.system(),'machine':platform.machine(),'logical_cpu_count':os.cpu_count(),'training_device':'CPU','accelerator_required':False,
          'available_memory_bytes':None,'free_disk_bytes':None};reasons=[]
    calibration=_calibrate(root,job,rows,settings,info,estimates)
    try:
        info['available_memory_bytes']=training_resources.available_memory();directory=Path(root)
        while not directory.exists() and directory!=directory.parent:directory=directory.parent
        info['free_disk_bytes']=shutil.disk_usage(directory).free
        if info['available_memory_bytes']<estimates['required_available_memory_bytes'] or info['free_disk_bytes']<estimates['required_free_disk_bytes']:reasons.append('Available memory or disk does not cover this image recipe. Review a smaller dataset or close other apps before retrying.')
    except (OSError,ValueError,AttributeError,subprocess.SubprocessError):reasons.append('CPU memory/disk availability could not be checked.')
    report={'format':'almg-image-feasibility-v1','schema_version':1,'job_id':job['id'],'recipe':'text_to_image','mode':job.get('mode'),'variant':variant,
            'settings':settings,'dataset_sha256':digest(rows),'hardware':info,'estimates':estimates,'calibration':calibration,'feasible':not reasons,'blockers':reasons,'implementation_sha256':file_digest(Path(__file__))}
    report['revision']=digest(report)
    return report


def admit(root,job,rows,parameters,approved=None):
    fresh=review(root,job,rows,parameters)
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(key)!=fresh[key] for key in ('format','schema_version','job_id','recipe','mode','variant','settings','dataset_sha256','estimates','calibration','implementation_sha256'))):raise ValueError('Image resource review changed; reopen feasibility before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('CPU image training blocked: '+' '.join(fresh['blockers']))
    return fresh


def attach_manifest(job,manifest):
    if job.get('image_feasibility'):
        manifest={**manifest,'image_hardware':{name:deepcopy(job.get(key,job['image_feasibility'])) for name,key in
                  (('approval','image_feasibility'),('admission','image_admission_feasibility'),('execution','image_execution_feasibility'))}}
    return validate_manifest(manifest)


def validate_manifest(manifest):
    for report in manifest.get('image_hardware',{}).values():
        if (report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'}) or report.get('job_id')!=manifest['job_id'] or report.get('feasible') is not True
                or report.get('dataset_sha256')!=manifest.get('approval',{}).get('binding',{}).get('prepared_dataset_sha256',manifest['dataset']['sha256'])):raise ValueError('Image hardware profile changed.')
    return manifest
