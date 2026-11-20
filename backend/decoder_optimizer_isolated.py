"""Fresh-process optimizer execution; retained training artifacts are never deleted."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
if __package__:
    from . import decoder_optimizer_fixture as fixture
else:
    import decoder_optimizer_fixture as fixture


def run(root,plan_id,confirmed,initialized,settings,approved):
    if confirmed is not True:raise ValueError('Explicitly approve optimizer training before starting an isolated worker.')
    current=fixture.review(root,plan_id,initialized,settings)
    if not isinstance(approved,dict) or approved.get('revision')!=fixture.digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','config','model_config','runtime','estimates','implementation_sha256')):raise ValueError('Optimizer review changed; reopen it before training.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Isolated optimizer training is blocked by hardware/resources.')
    nonce=uuid.uuid4().hex
    payload={'root':str(Path(root).resolve()),'plan_id':plan_id,'initialized':initialized,'settings':settings,'approved':approved,'nonce':nonce}
    serialized=json.dumps(payload,allow_nan=False)
    process=subprocess.Popen([sys.executable,'-m','backend.decoder_optimizer_worker'],cwd=str(Path(__file__).resolve().parent.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(serialized,timeout=120)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate()
        raise ValueError('Isolated optimizer worker timed out; any saved artifacts were retained.')
    if process.returncode:raise ValueError('Isolated optimizer worker failed; any saved artifacts were retained. '+stderr[-600:])
    response=json.loads(stdout);record=fixture.read(root,response['record_id']);observed=record.get('isolated_workflow_measurements',{})
    if (response.get('nonce')!=nonce or response.get('process_id')!=process.pid or process.pid==os.getpid()
        or observed.get('format')!='almg-isolated-optimizer-measurements-v1' or observed.get('scope')!='fresh_process_bounded_optimizer_fixture'
        or observed.get('process_id')!=process.pid or observed.get('isolated_trial_peak_measured') is not True
        or record.get('approved_review')!=approved or record['review']['source']['plan_id']!=plan_id):raise ValueError('Isolated optimizer result binding failed; retained artifacts need review.')
    return record
