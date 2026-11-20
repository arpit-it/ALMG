"""One approved corpus training workflow per fresh process; preserve all artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
if __package__:
    from . import decoder_corpus_optimizer as training
else:
    import decoder_corpus_optimizer as training


def review(root,initialized,corpus,settings):
    return training.review(root,initialized,corpus,settings,'fresh_process')


def run(root,confirmed,initialized,corpus,settings,approved,request_id=None):
    if confirmed is not True:raise ValueError('Explicitly confirm corpus training before launching a worker.')
    if request_id is not None:training.run_cancellation.validate(request_id)
    current=review(root,initialized,corpus,settings)
    keys=('format','schema_version','source','corpus_id','corpus_revision','config','model_config','runtime','estimates','implementation_sha256','execution_mode')
    if (not isinstance(approved,dict) or approved.get('revision')!=training.digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(key)!=current[key] for key in keys)):
        raise ValueError('Corpus worker review changed; reopen it before training.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Isolated corpus training is blocked by current resources.')
    return _execute(root,{'initialized':initialized,'corpus':corpus,'settings':settings,'request_id':request_id},approved,'full')


def _execute(root,payload,approved,action):
    nonce=uuid.uuid4().hex;expected_token=payload.get('request_id')
    payload=json.dumps({**payload,'root':str(Path(root).resolve()),'approved':approved,'nonce':nonce,'action':action},allow_nan=False)
    process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],cwd=str(Path(__file__).resolve().parent.parent),
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(payload,timeout=120)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate()
        raise ValueError('Corpus worker timed out; any saved model/checkpoint artifacts are retained.')
    if process.returncode:raise ValueError('Corpus worker failed; any saved artifacts are retained. '+stderr[-600:])
    response=json.loads(stdout)
    if action in ('full','reference_resume'):record=training.read(root,response['record_id']);observed=training.feedback.measurements(record)
    else:
        module=_continuations();record=module.read(root,response['record_id']);observed=module.measured_feedback.measurements(record)
    if action=='reference_resume' and record['review'].get('reference_resume_from')!=approved.get('reference_resume_from'):raise ValueError('Retained reference worker source changed.')
    expected=approved['corpus_id'] if action in ('full','reference_resume') else (approved['source']['record_id'] if action=='continuation' else approved['resume_from']['record_id'])
    actual=record['review']['corpus_id'] if action in ('full','reference_resume') else (record['review']['source']['record_id'] if action=='continuation' else record['review']['resume_from']['record_id'])
    if (response.get('nonce')!=nonce or response.get('process_id')!=process.pid or process.pid==os.getpid()
            or observed is None or observed['process_id']!=process.pid or record['review']!=approved or record.get('request_id')!=expected_token
            or record['review']['execution_mode']!='fresh_process' or actual!=expected):
        raise ValueError('Isolated corpus result binding changed; retained artifacts require review.')
    return record


def _continuations():
    if __package__:from . import decoder_corpus_continuations
    else:import decoder_corpus_continuations
    return decoder_corpus_continuations


def review_continuation(root,identifier):
    return _continuations().review(root,identifier,execution_mode='fresh_process')


def review_partial(root,identifier):
    return _continuations().review_partial(root,identifier,execution_mode='fresh_process')


def _recover(root,identifier,confirmed,approved,request_id,action):
    if confirmed is not True:raise ValueError('Explicitly confirm the isolated corpus checkpoint recovery.')
    module=_continuations()
    if request_id is not None:module.cancellation.validate(request_id)
    current=review_continuation(root,identifier) if action=='continuation' else review_partial(root,identifier)
    keys=('format','schema_version','source','resume_from','restore_step','corpus_id','corpus_revision','config','runtime','estimates','implementation_sha256','execution_mode')
    if (not isinstance(approved,dict) or approved.get('revision')!=training.digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(key)!=current[key] for key in keys)):
        raise ValueError('Corpus recovery worker review changed; reopen it before confirming.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Isolated corpus recovery is blocked by current resources.')
    return _execute(root,{'identifier':identifier,'request_id':request_id},approved,action)


def run_continuation(root,identifier,confirmed,approved,request_id=None):
    return _recover(root,identifier,confirmed,approved,request_id,'continuation')


def run_partial(root,identifier,confirmed,approved,request_id=None):
    return _recover(root,identifier,confirmed,approved,request_id,'partial_resume')


def review_reference_resume(root,identifier):
    if __package__:from . import decoder_corpus_reference_resume
    else:import decoder_corpus_reference_resume
    return decoder_corpus_reference_resume.review(root,identifier)


def run_reference_resume(root,identifier,confirmed,approved,request_id=None):
    if confirmed is not True:raise ValueError('Explicitly confirm retained reference resume.')
    if request_id is not None:training.run_cancellation.validate(request_id)
    current=review_reference_resume(root,identifier)
    keys=('format','schema_version','reference_resume_from','source','corpus_id','corpus_revision','config','model_config','runtime','estimates','implementation_sha256','execution_mode')
    if (not isinstance(approved,dict) or approved.get('revision')!=training.digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(key)!=current.get(key) for key in keys)):
        raise ValueError('Retained reference review changed; reopen it before confirming.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Reference resume is blocked by current resources.')
    return _execute(root,{'identifier':identifier,'request_id':request_id},approved,'reference_resume')
