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


def run(root,confirmed,initialized,corpus,settings,approved):
    if confirmed is not True:raise ValueError('Explicitly confirm corpus training before launching a worker.')
    current=review(root,initialized,corpus,settings)
    keys=('format','schema_version','source','corpus_id','corpus_revision','config','model_config','runtime','estimates','implementation_sha256','execution_mode')
    if (not isinstance(approved,dict) or approved.get('revision')!=training.digest({k:v for k,v in approved.items() if k!='revision'})
            or any(approved.get(key)!=current[key] for key in keys)):
        raise ValueError('Corpus worker review changed; reopen it before training.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Isolated corpus training is blocked by current resources.')
    nonce=uuid.uuid4().hex
    payload=json.dumps({'root':str(Path(root).resolve()),'initialized':initialized,'corpus':corpus,'settings':settings,'approved':approved,'nonce':nonce},allow_nan=False)
    process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],cwd=str(Path(__file__).resolve().parent.parent),
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(payload,timeout=120)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate()
        raise ValueError('Corpus worker timed out; any saved model/checkpoint artifacts are retained.')
    if process.returncode:raise ValueError('Corpus worker failed; any saved artifacts are retained. '+stderr[-600:])
    response=json.loads(stdout);record=training.read(root,response['record_id']);observed=training.feedback.measurements(record)
    if (response.get('nonce')!=nonce or response.get('process_id')!=process.pid or process.pid==os.getpid()
            or observed is None or observed['process_id']!=process.pid or record['review']!=approved
            or record['review']['execution_mode']!='fresh_process' or record['review']['corpus_id']!=corpus['id']
            or record['review']['corpus_revision']!=corpus['revision']):
        raise ValueError('Isolated corpus result binding changed; retained artifacts require review.')
    return record
