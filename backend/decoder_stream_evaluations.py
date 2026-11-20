"""Independent full held-out CPU evaluation of completed immutable stream trials."""
import json
from pathlib import Path
import uuid
if __package__:
    from . import decoder_stream_training as training, decoder_stream_optimization as core, decoder_bundle, training_resources
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_training as training, decoder_stream_optimization as core, decoder_bundle, training_resources
    from run_manifest import digest, file_digest


def _folder(root,run_id):
    training._folder(root,run_id)
    return Path(root)/'decoder-stream-training-evaluations'/run_id


def _validated(root,run_id,revision):
    state=training.read(root,run_id)
    if state['revision']!=revision or state['status']!='complete' or state['completed_steps']!=20 or state['evaluation'] is None:
        raise ValueError('Reopen the exact completed streamed trial before independent evaluation.')
    training.batches._validated(root,state['windows_id'],state['review']['windows'])
    return state


def evaluate(root,run_id,confirmed,reviewed_revision):
    if confirmed is not True:raise ValueError('Confirm full held-out CPU evaluation and saving a private report.')
    state=_validated(root,run_id,reviewed_revision)
    training_resources.check_size(65536,Path(root))
    bundle=training._folder(root,run_id)/state['checkpoint']
    model,tokenizer,_=decoder_bundle.load(bundle)
    import numpy as np
    def score(batch):
        targets=np.array(batch['targets'],dtype=np.int64);mask=np.array(batch['loss_mask'],dtype=np.float64)
        try:
            with np.errstate(over='raise',invalid='raise',divide='raise'):
                scores=model.logits(batch['inputs']).astype(np.float64)
                if not np.isfinite(scores).all():raise ValueError('Nonfinite CPU evaluation scores; no report saved.')
                maximum=np.max(scores,axis=-1)
                selected=np.take_along_axis(scores,targets[...,None],axis=-1).squeeze(-1)
                losses=maximum+np.log(np.sum(np.exp(scores-maximum[...,None]),axis=-1))-selected
                return float(np.sum(losses*mask)),int(np.sum((np.argmax(scores,axis=-1)==targets)*mask))
        except FloatingPointError as error:raise ValueError('Invalid CPU evaluation scores; no report saved.') from error
    evaluation={part:core.evaluate_split(root,state['windows_id'],state['review']['windows'],part,score,batch_worker=training.batches) for part in ('validation','test')}
    comparison={part:{'absolute_loss_difference':abs(evaluation[part]['loss']-state['evaluation'][part]['loss']),
                      'absolute_accuracy_difference':abs(evaluation[part]['next_token_accuracy']-state['evaluation'][part]['next_token_accuracy'])} for part in evaluation}
    target=state['approval']['settings']['quality_target']
    record={'format':'almg-stream-cpu-evaluation-v1','schema_version':1,'evaluation_version':1,'id':uuid.uuid4().hex,
            'run_id':run_id,'run_revision':state['revision'],'windows_id':state['windows_id'],'windows_revision':state['review']['windows']['revision'],
            'checkpoint_manifest_sha256':state['checkpoint_manifest_sha256'],'tokenizer_sha256':tokenizer.fingerprint(),
            'runtime':{'device':'CPU','numpy':np.__version__},'evaluation':evaluation,'comparison_to_training':comparison,
            'target_next_token_accuracy':target,'passed':all(value['next_token_accuracy']>=target for value in evaluation.values()),
            'release_approved':False,'optimizer_updates':0,'implementation_sha256':file_digest(Path(__file__)),
            'scope':'independent_all_saved_heldout_windows_no_training_or_release'}
    if _validated(root,run_id,reviewed_revision)!=state:raise ValueError('Trial/source bindings changed during CPU evaluation; no report saved.')
    decoder_bundle.load(bundle)
    if file_digest(bundle/'manifest.json')!=state['checkpoint_manifest_sha256']:raise ValueError('Checkpoint changed during CPU evaluation.')
    record['revision']=digest(record);serialized=json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2)
    if len(serialized.encode('utf-8'))>256000:raise ValueError('CPU evaluation report exceeds its record limit.')
    parent=_folder(root,run_id);parent.mkdir(parents=True,exist_ok=True);temporary=parent/(record['id']+'.tmp')
    try:
        temporary.write_text(serialized,encoding='utf-8');temporary.replace(parent/(record['id']+'.json'))
    finally:temporary.unlink(missing_ok=True)
    return record


def list_reports(root,run_id,confirmed,reviewed_revision):
    if confirmed is not True:raise ValueError('Confirm review of private independent evaluation reports.')
    state=_validated(root,run_id,reviewed_revision);parent=_folder(root,run_id);reports=[]
    for path in sorted(parent.glob('*.json')) if parent.exists() else []:
        try:
            if path.stat().st_size>256000:continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if (record.get('format')!='almg-stream-cpu-evaluation-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
                    or type(record.get('evaluation_version')) is not int or record['evaluation_version']!=1
                    or record.get('id')!=path.stem or record.get('run_id')!=run_id or record.get('run_revision')!=state['revision']
                    or record.get('checkpoint_manifest_sha256')!=state['checkpoint_manifest_sha256'] or record.get('release_approved') is not False
                    or type(record.get('optimizer_updates')) is not int or record['optimizer_updates']!=0
                    or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):continue
            reports.append(record)
        except (OSError,ValueError,TypeError,KeyError):continue
    return reports[-20:]
