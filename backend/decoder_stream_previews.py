"""Consent-bound CPU previews of completed streamed trials; no training or release."""
import json
from pathlib import Path
import uuid
if __package__:
    from . import decoder_stream_training as training, decoder_bundle, training_resources
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_training as training, decoder_bundle, training_resources
    from run_manifest import digest, file_digest


def _folder(root,run_id):
    training._folder(root,run_id)
    return Path(root)/'decoder-stream-training-previews'/run_id


def _validated(root,run_id,revision):
    state=training.read(root,run_id)
    if state['revision']!=revision or state['status']!='complete' or state['completed_steps']!=20 or state['evaluation'] is None:
        raise ValueError('Reopen the exact completed streamed trial before private inference.')
    training.batches._validated(root,state['windows_id'],state['review']['windows'])
    return state


def preview(root,run_id,confirmed,reviewed_revision,prompt,max_new_tokens=12,persist=True):
    if confirmed is not True:raise ValueError('Confirm local inference and saving this private prompt/output.')
    if not isinstance(prompt,str) or not 1<=len(prompt)<=4096:raise ValueError('Provide an exact prompt of 1 to 4096 characters.')
    if type(max_new_tokens) is not int or not 1<=max_new_tokens<=32:raise ValueError('Generate 1 to 32 new token IDs.')
    state=_validated(root,run_id,reviewed_revision)
    training_resources.check_size(65536,Path(root))
    bundle=training._folder(root,run_id)/state['checkpoint']
    model,tokenizer,manifest=decoder_bundle.load(bundle)
    tokens=tokenizer.encode(prompt)
    if len(tokens)>model.config['context_length']:raise ValueError('The exact prompt exceeds the saved 16-token context; shorten it. No truncation or tokenizer refitting is performed.')
    prompt_ids=list(tokens);generated=[]
    import numpy as np
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            for _ in range(max_new_tokens):
                scores=model.logits([tokens[-model.config['context_length']:]])[0,-1]
                if not np.isfinite(scores).all():raise ValueError('Nonfinite private inference scores; no preview saved.')
                token=int(np.argmax(scores));tokens.append(token);generated.append(token)
    except FloatingPointError as error:raise ValueError('Invalid private inference scores; no preview saved.') from error
    result={'format':'almg-stream-training-preview-v1','schema_version':1,'id':uuid.uuid4().hex,'run_id':run_id,'run_revision':state['revision'],
            'checkpoint_manifest_sha256':state['checkpoint_manifest_sha256'],'tokenizer_sha256':tokenizer.fingerprint(),
            'prompt':prompt,'prompt_token_ids':prompt_ids,'generated_token_ids':generated,
            'completion':tokenizer.decode_preview(generated),'text':tokenizer.decode_preview(tokens),
            'inference':{'algorithm':'greedy','runtime':'numpy_cpu','max_new_tokens':max_new_tokens,'context_policy':'sliding_window_16',
                         'generated_decode_policy':tokenizer.artifact()['generated_decode_policy'],'implementation_sha256':file_digest(Path(__file__))},
            'quality_target_met':state['quality_target_met'],'release_approved':False,'optimizer_updates':0,
            'scope':'private_completed_stream_trial_preview_no_quality_or_release_claim'}
    if _validated(root,run_id,reviewed_revision)!=state:raise ValueError('Trial or source bindings changed during inference; no preview saved.')
    # Recheck checkpoint files, including parameter/tokenizer hashes, at publication.
    decoder_bundle.load(bundle)
    if file_digest(bundle/'manifest.json')!=state['checkpoint_manifest_sha256']:raise ValueError('Checkpoint changed during inference.')
    result['revision']=digest(result)
    serialized=json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)
    if len(serialized.encode('utf-8'))>1024*1024:raise ValueError('Private preview exceeds its saved record limit.')
    if persist is False:return result
    parent=_folder(root,run_id);parent.mkdir(parents=True,exist_ok=True);temporary=parent/(result['id']+'.tmp')
    try:
        temporary.write_text(serialized,encoding='utf-8')
        temporary.replace(parent/(result['id']+'.json'))
    finally:temporary.unlink(missing_ok=True)
    return result


def list_previews(root,run_id,confirmed,reviewed_revision):
    if confirmed is not True:raise ValueError('Confirm review of saved private prompts and outputs.')
    state=_validated(root,run_id,reviewed_revision);result=[];parent=_folder(root,run_id)
    for path in sorted(parent.glob('*.json')) if parent.exists() else []:
        try:
            if path.stat().st_size>1024*1024:continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if (record.get('format')!='almg-stream-training-preview-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
                    or record.get('id')!=path.stem or record.get('run_id')!=run_id or record.get('run_revision')!=state['revision']
                    or record.get('checkpoint_manifest_sha256')!=state['checkpoint_manifest_sha256'] or record.get('release_approved') is not False
                    or type(record.get('optimizer_updates')) is not int or record['optimizer_updates']!=0
                    or record.get('revision')!=digest({key:value for key,value in record.items() if key!='revision'})):continue
            result.append(record)
        except (OSError,ValueError,KeyError,TypeError):continue
    return result[-20:]
