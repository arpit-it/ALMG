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
    return _execute(root,{'plan_id':plan_id,'initialized':initialized,'settings':settings},approved,fixture.read,'plan_id',plan_id,'fixture')


def run_continuation(root,identifier,confirmed,approved,request_id=None):
    if confirmed is not True:raise ValueError('Explicitly approve checkpoint continuation before starting an isolated worker.')
    if __package__:from . import decoder_optimizer_continuations as continuations
    else:import decoder_optimizer_continuations as continuations
    if request_id is not None:continuations.cancellation.validate(request_id)
    current=continuations.review(root,identifier)
    if not isinstance(approved,dict) or approved.get('revision')!=fixture.digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','resume_from','restore_step','config','runtime','estimates','implementation_sha256')):raise ValueError('Checkpoint continuation review changed; reopen it before approval.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Isolated checkpoint continuation is blocked by hardware/resources.')
    return _execute(root,{'identifier':identifier,'request_id':request_id},approved,continuations.read,'record_id',identifier,'continuation')


def run_partial(root,identifier,confirmed,approved,request_id=None):
    if confirmed is not True:raise ValueError('Explicitly approve resuming the retained partial checkpoint.')
    if __package__:from . import decoder_optimizer_continuations as continuations
    else:import decoder_optimizer_continuations as continuations
    if request_id is not None:continuations.cancellation.validate(request_id)
    current=continuations.review_partial(root,identifier)
    if not isinstance(approved,dict) or approved.get('revision')!=fixture.digest({k:v for k,v in approved.items() if k!='revision'}) or any(approved.get(key)!=current[key] for key in ('format','schema_version','source','resume_from','restore_step','config','runtime','estimates','implementation_sha256')):raise ValueError('Partial checkpoint review changed; reopen it before approval.')
    if not current['feasible'] or approved.get('feasible') is not True:raise ValueError('Partial checkpoint resume is blocked by hardware/resources.')
    return _execute(root,{'identifier':identifier,'request_id':request_id},approved,continuations.read,'record_id',identifier,'partial_resume')


def _execute(root,payload,approved,reader,source_key,source_id,kind):
    expected_format='almg-isolated-optimizer-continuation-measurements-v1' if kind in ('continuation','partial_resume') else 'almg-isolated-optimizer-measurements-v1'
    expected_scope='fresh_process_optimizer_checkpoint_continuation' if kind in ('continuation','partial_resume') else 'fresh_process_bounded_optimizer_fixture'
    nonce=uuid.uuid4().hex
    payload={**payload,'root':str(Path(root).resolve()),'approved':approved,'nonce':nonce,'action':kind}
    serialized=json.dumps(payload,allow_nan=False)
    process=subprocess.Popen([sys.executable,'-m','backend.decoder_optimizer_worker'],cwd=str(Path(__file__).resolve().parent.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(serialized,timeout=120)
    except subprocess.TimeoutExpired:
        process.kill();process.communicate()
        raise ValueError('Isolated optimizer worker timed out; any saved artifacts were retained.')
    if process.returncode:raise ValueError('Isolated optimizer worker failed; any saved artifacts were retained. '+stderr[-600:])
    response=json.loads(stdout);record=reader(root,response['record_id']);observed=record.get('isolated_workflow_measurements',{})
    bound_source=record['review']['resume_from'] if kind=='partial_resume' else record['review']['source']
    if (response.get('nonce')!=nonce or response.get('process_id')!=process.pid or process.pid==os.getpid()
        or observed.get('format')!=expected_format or observed.get('scope')!=expected_scope
        or observed.get('process_id')!=process.pid or observed.get('isolated_trial_peak_measured') is not True
        or record.get('approved_review')!=approved or bound_source[source_key]!=source_id):raise ValueError('Isolated optimizer result binding failed; retained artifacts need review.')
    return record
