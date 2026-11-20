"""Isolated chunk execution and immutable checkpoint-bound observations."""
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile
from time import perf_counter
if __package__:
    from . import decoder_stream_training as training
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_training as training
    from run_manifest import digest,file_digest


def execute(root,before,admission,started=None):
    started=perf_counter() if started is None else started
    payload={'root':str(Path(root).resolve()),'run_id':before['id'],'expected_revision':before['revision']}
    try:result=subprocess.run([sys.executable,str(Path(__file__).with_name('decoder_stream_chunk_worker.py'))],input=json.dumps(payload),text=True,capture_output=True,timeout=120,check=False)
    except subprocess.TimeoutExpired as error:raise ValueError('Streamed worker timed out. Reopen saved trials to inspect the last committed checkpoint before retrying.') from error
    try:output=json.loads(result.stdout)
    except (ValueError,TypeError) as error:raise ValueError('Invalid streamed worker response. Reopen saved trials to inspect checkpoint state.') from error
    if not isinstance(output,dict) or result.returncode:raise ValueError('Streamed worker failed; reopen saved trials to inspect the last checkpoint. '+str(output.get('error','') if isinstance(output,dict) else 'Invalid response'))
    if not isinstance(output.get('state'),dict) or not isinstance(output.get('measurements'),dict) or not isinstance(output.get('admission'),dict):raise ValueError('Incomplete streamed worker response; inspect saved trial state.')
    state=training.read(root,before['id']);observed=output['measurements']
    observed['request_work_seconds']=perf_counter()-started
    if (output['state']!=state or state['completed_steps']!=before['completed_steps']+5 or state['approval']!=before['approval']
            or not _valid_observations(observed)):raise ValueError('Streamed worker/checkpoint binding changed; inspect saved trial state.')
    record={'format':'almg-stream-chunk-measurements-v1','schema_version':1,'run_id':state['id'],
            'before_revision':before['revision'],'after_revision':state['revision'],'completed_steps':state['completed_steps'],
            'approval_sha256':digest(state['approval']),'training_review_sha256':digest(state['review']),
            'checkpoint':state['checkpoint'],'checkpoint_manifest_sha256':state['checkpoint_manifest_sha256'],
            'parent_admission':admission,'execution_admission':output['admission'],'measurements':observed,
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_stream_training_measurements.py','decoder_stream_chunk_worker.py')})}
    record['revision']=digest(record)
    try:_publish(training._folder(root,state['id'])/'continuation-measurements',record)
    except OSError as error:raise ValueError(f"Training reached {state['completed_steps']} updates, but measurement publication failed. Its checkpoint is retained; reopen saved trials.") from error
    return state


def _valid_observations(value):
    return (isinstance(value,dict) and value.get('isolated_process') is True and value.get('updates')==5
            and all(type(value.get(key)) in (float,int) and math.isfinite(value[key]) and value[key]>0 for key in ('elapsed_seconds','request_work_seconds'))
            and all(type(value.get(key)) is int and value[key]>0 for key in ('metal_peak_bytes','process_peak_rss_bytes','process_id')))


def _publish(directory,record):
    directory.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,prefix='.chunk-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(json.dumps(record,allow_nan=False,indent=2))
        temporary.replace(directory/(record['after_revision']+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def read(root,run_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of private streamed chunk measurements.')
    state=training.read(root,run_id);directory=training._folder(root,run_id);records=[]
    for path in (directory/'continuation-measurements').glob('*.json'):
        try:
            if path.stat().st_size>128000:continue
            record=json.loads(path.read_text(encoding='utf-8'));checkpoint=record['checkpoint'];observed=record['measurements']
            if (record.get('format')!='almg-stream-chunk-measurements-v1' or record.get('schema_version')!=1 or record.get('run_id')!=run_id
                    or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'}) or record.get('after_revision')!=path.stem
                    or record.get('approval_sha256')!=digest(state['approval']) or record.get('training_review_sha256')!=digest(state['review'])
                    or type(record.get('completed_steps')) is not int or record['completed_steps'] not in (5,10,15,20) or record['completed_steps']>state['completed_steps']
                    or not _valid_observations(observed) or observed.get('includes_final_heldout_evaluation')!=(record['completed_steps']==20)
                    or not isinstance(checkpoint,str) or Path(checkpoint).name!=checkpoint):continue
            if file_digest(directory/checkpoint/'manifest.json')!=record['checkpoint_manifest_sha256']:continue
            _,_,manifest=training.decoder_bundle.load(directory/checkpoint)
            if manifest['training']['completed_steps']!=record['completed_steps'] or manifest['training']['approval_sha256']!=record['approval_sha256']:continue
            for key in ('parent_admission','execution_admission'):
                report=record[key]
                if report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'}) or report.get('feasible') is not True or report.get('training_review_sha256')!=record['training_review_sha256']:raise ValueError('Admission snapshot changed.')
            records.append(record)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
    records.sort(key=lambda record:record['completed_steps'])
    nonfinal=[r['measurements']['request_work_seconds'] for r in records if not r['measurements']['includes_final_heldout_evaluation']]
    remaining=(20-state['completed_steps'])//5
    return {'records':records,'completed_steps':state['completed_steps'],
            'estimated_remaining_update_checkpoint_seconds':max(nonfinal)*remaining if nonfinal else None,
            'remaining_chunks':remaining,'duration_policy':'Largest observed same-run nonfinal chunk request work multiplied by remaining chunks. Includes admission and worker startup; excludes lock queue, measurement publication, final held-out evaluation and manual pauses. Hardware/load changes can invalidate comparison. Not a full-training duration prediction or guarantee.'}
