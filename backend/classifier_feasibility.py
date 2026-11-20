"""Read-only CPU admission for the existing bounded classifier comparison."""
import json
import math
from importlib.metadata import version
from copy import deepcopy
import os
from pathlib import Path
import platform
import shutil
import subprocess
if __package__:
    from . import recipe_contracts,training_resources
    from .run_manifest import digest,file_digest
else:
    import recipe_contracts,training_resources
    from run_manifest import digest,file_digest



def _calibrate(root, job, rows, settings, hardware, estimates):
    # Local import avoids a module cycle: trials use fresh feasibility admission.
    if __package__:
        from . import classifier_resource_trials
    else:
        import classifier_resource_trials
    producer = digest({name: file_digest(Path(__file__).with_name(name)) for name in
                       ('classifier_resource_trials.py', 'classifier_trial_worker.py', 'studio.py', 'recipe_contracts.py')})
    runtime = {'python': platform.python_version(), 'system': platform.system(),
               'machine': platform.machine(), 'sklearn': version('scikit-learn')}
    compatible = []
    for record in classifier_resource_trials.read(root, job['id'])['records']:
        observed = record.get('measurements', {})
        admission = record.get('admission', {})
        peak = observed.get('process_peak_rss_bytes')
        seconds = observed.get('fit_and_validation_seconds')
        if (record.get('dataset_sha256') != digest(rows) or record.get('settings') != settings
                or record.get('implementation_sha256') != producer
                or admission.get('implementation_sha256') != file_digest(Path(__file__))
                or admission.get('labels') != job['plan']['labels']
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
    return {'trial_ids': [record['id'] for record in compatible], 'measured_process_peak_rss_bytes': peak,
            'memory_reserve_multiplier': 1.25, 'measured_fit_and_validation_seconds': seconds,
            'scope': 'Same prepared dataset/settings, CPU topology, runtime and implementation only. Highest observed discarded fit; not a full training duration or exhaustion guarantee. Memory reserves only increase; disk remains calculated. Repair, idle waits, imports and candidate persistence are excluded from measured time.'}


def review(root,job,rows,parameters):
    if job.get('recipe','classifier')!='classifier':raise ValueError('Choose the CPU classifier recipe.')
    settings=recipe_contracts.training_parameters('classifier',parameters,job.get('recipe_contract'))
    encoded=len(json.dumps(rows,ensure_ascii=False).encode('utf-8'));classes=len(job['plan']['labels'])
    # Candidate implementations cap TF-IDF at 30,000 features; no dense row/feature matrix is promised.
    coefficients=30000*max(2,classes)*8*32
    estimates={'dataset_encoded_bytes':encoded,'coefficient_comparison_budget_bytes':coefficients,
               'required_available_memory_bytes':256*1024**2+encoded*8+coefficients,
               'required_free_disk_bytes':64*1024**2+encoded*4+coefficients*2,
               'measured':False,'duration_estimate_seconds':None,
               'assumptions':'CPU scikit-learn sparse TF-IDF comparison with at most 30,000 features per candidate. A 32-copy coefficient allowance includes solver history/workspace and retained candidates; dataset expansion and vocabulary overhead are estimated, not measured. Optional Qwen repair planning is separate. Not an exhaustion guarantee.'}
    info={'system':platform.system(),'machine':platform.machine(),'logical_cpu_count':os.cpu_count(),
          'training_device':'CPU','accelerator_required':False,'gpu_fallback_required':False,
          'available_memory_bytes':None,'free_disk_bytes':None};reasons=[]
    calibration=_calibrate(root,job,rows,settings,info,estimates)
    try:
        info['available_memory_bytes']=training_resources.available_memory();directory=Path(root)
        while not directory.exists() and directory!=directory.parent:directory=directory.parent
        info['free_disk_bytes']=shutil.disk_usage(directory).free
        if info['available_memory_bytes']<estimates['required_available_memory_bytes'] or info['free_disk_bytes']<estimates['required_free_disk_bytes']:reasons.append('Available memory or disk does not cover the CPU classifier reserves.')
    except (OSError,ValueError,AttributeError,subprocess.SubprocessError):reasons.append('CPU memory/disk availability could not be checked.')
    record={'format':'almg-classifier-feasibility-v1','schema_version':1,'job_id':job['id'],'recipe':'classifier','settings':settings,
            'dataset_sha256':digest(rows),'labels':job['plan']['labels'],'hardware':info,'estimates':estimates,'calibration':calibration,'feasible':not reasons,'blockers':reasons,
            'scope':'prepared_classifier_dataset_cpu_only_no_gpu_or_neural_training_claim','implementation_sha256':file_digest(Path(__file__))}
    record['revision']=digest(record)
    return record


def admit(root,job,rows,parameters,approved=None):
    fresh=review(root,job,rows,parameters)
    if approved is not None and (not isinstance(approved,dict) or approved.get('feasible') is not True
            or approved.get('revision')!=digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(k)!=fresh[k] for k in ('format','schema_version','job_id','recipe','settings','dataset_sha256','labels','estimates','calibration','implementation_sha256'))):raise ValueError('CPU classifier review changed; reopen feasibility before approval.')
    if not fresh['feasible']:raise training_resources.ResourceUnavailable('CPU classifier blocked: '+' '.join(fresh['blockers']))
    return fresh


def attach_manifest(job,manifest):
    if job.get('classifier_feasibility'):
        manifest={**manifest,'classifier_hardware':{'approval':deepcopy(job['classifier_feasibility']),
                  'admission':deepcopy(job.get('classifier_admission_feasibility',job['classifier_feasibility'])),
                  'execution':deepcopy(job.get('classifier_execution_feasibility',job['classifier_feasibility']))}}
    return validate_manifest(manifest)


def validate_manifest(manifest):
    for report in manifest.get('classifier_hardware',{}).values():
        if (report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'}) or report.get('job_id')!=manifest['job_id']
                or report.get('dataset_sha256')!=manifest.get('approval',{}).get('binding',{}).get('prepared_dataset_sha256',manifest['dataset']['sha256'])
                or report.get('feasible') is not True):raise ValueError('Classifier hardware profile changed.')
    return manifest
