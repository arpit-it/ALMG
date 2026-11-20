"""Separately approved isolated CPU measurements; main job stays dataset-ready."""
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
import uuid
from datetime import datetime,timezone
if __package__:
    from . import classifier_feasibility
    from .run_manifest import digest,file_digest
else:
    import classifier_feasibility
    from run_manifest import digest,file_digest


def _folder(root,job_id):
    if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('Invalid classifier job ID.')
    return Path(root)/'classifier-resource-trials'/job_id


def run(root,job,rows,settings,confirmed,approved):
    if confirmed is not True:raise ValueError('Confirm a discarded CPU resource trial separately from main training.')
    if not isinstance(approved,dict):raise ValueError('Review the exact CPU feasibility report before a discarded trial.')
    admission=classifier_feasibility.admit(root,job,rows,settings,approved)
    if admission['settings'].get('allow_repair'):raise ValueError('Turn off optional Qwen repair for this CPU-only resource trial.')
    path=Path(root)/'training-sessions'/job['id']/'dataset.json'
    if digest(json.loads(path.read_text(encoding='utf-8')))!=admission['dataset_sha256']:raise ValueError('Persist the reviewed dataset before a CPU resource trial.')
    request={'dataset_path':str(path.resolve()),'dataset_sha256':admission['dataset_sha256'],'settings':admission['settings'],'mode':job.get('mode'),'labels':job['plan']['labels']}
    try:result=subprocess.run([sys.executable,str(Path(__file__).with_name('classifier_trial_worker.py'))],input=json.dumps(request),capture_output=True,text=True,timeout=120,check=False)
    except subprocess.TimeoutExpired as error:raise ValueError('CPU resource trial timed out; temporary models were discarded and no report was saved.') from error
    try:observed=json.loads(result.stdout)
    except (ValueError,TypeError) as error:raise ValueError('Invalid CPU resource trial result; no report saved.') from error
    if not isinstance(observed,dict) or result.returncode:raise ValueError('CPU resource trial failed: '+str(observed.get('error','invalid response') if isinstance(observed,dict) else 'invalid response'))
    if (observed.get('dataset_sha256')!=admission['dataset_sha256'] or observed.get('training_device')!='CPU' or observed.get('weights_retained') is not False
            or observed.get('isolated_process') is not True or type(observed.get('process_peak_rss_bytes')) is not int or observed['process_peak_rss_bytes']<=0
            or type(observed.get('fit_and_validation_seconds')) not in (int,float) or not math.isfinite(observed['fit_and_validation_seconds']) or observed['fit_and_validation_seconds']<=0):raise ValueError('Invalid CPU measurement binding.')
    if digest(json.loads(path.read_text(encoding='utf-8')))!=admission['dataset_sha256']:raise ValueError('Prepared dataset changed during CPU trial; no report saved.')
    record={'format':'almg-classifier-resource-trial-v1','schema_version':1,'id':uuid.uuid4().hex,'created_at':datetime.now(timezone.utc).isoformat(),'job_id':job['id'],'dataset_sha256':admission['dataset_sha256'],
            'settings':admission['settings'],'admission':admission,'measurements':observed,'training_approved':False,'release_approved':False,
            'limitations':'Process peak RSS includes interpreter/imports, prepared data and fit workspace. Fit time excludes interpreter/import startup, idle waits, Qwen repair and main candidate persistence. This discarded trial does not approve training/release or guarantee future resources.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('classifier_resource_trials.py','classifier_trial_worker.py','studio.py','recipe_contracts.py')})}
    record['revision']=digest(record);directory=_folder(root,job['id']);directory.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,prefix='.trial-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(json.dumps(record,allow_nan=False,indent=2))
        temporary.replace(directory/(record['id']+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return record


def read(root,job_id):
    records=[]
    for path in _folder(root,job_id).glob('*.json'):
        try:
            if path.stat().st_size>128000:continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if (record.get('format')=='almg-classifier-resource-trial-v1' and record.get('schema_version')==1 and record.get('id')==path.stem and record.get('job_id')==job_id
                    and record.get('revision')==digest({k:v for k,v in record.items() if k!='revision'}) and record.get('training_approved') is False and record.get('release_approved') is False):records.append(record)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
    return {'records':sorted(records,key=lambda record:(record.get('created_at',''),record['id']))[-20:]}
