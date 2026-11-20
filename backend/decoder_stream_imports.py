"""Bounded isolated streamed-archive imports; archived quality claims are unverified."""
import base64
from datetime import datetime,timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import stat
import threading
from tempfile import TemporaryDirectory
import uuid
import zipfile
if __package__:
    from . import decoder_bundle,decoder_stream_training as training,training_resources
    from .run_manifest import digest,file_digest
else:
    import decoder_bundle,decoder_stream_training as training,training_resources
    from run_manifest import digest,file_digest
FORMAT='almg-private-stream-decoder-import-v1'
_LOCK=threading.RLock()
LIMITS={'bundle/decoder.json':4*1024*1024,'bundle/tokenizer.json':128*1024,'bundle/manifest.json':256*1024,
        'evaluation.json':256000,'preview.json':1024*1024,'export-manifest.json':256000}


def _folder(root,identifier):
    training._folder(root,identifier)
    return Path(root)/'decoder-stream-training-imports'/identifier


def _infer(folder,prompt,count):
    if not isinstance(prompt,str) or not 1<=len(prompt)<=4096:raise ValueError('Provide an exact prompt of 1 to 4096 characters.')
    if type(count) is not int or not 1<=count<=32:raise ValueError('Generate 1 to 32 new IDs.')
    model,codec,_=decoder_bundle.load(folder/'bundle');tokens=codec.encode(prompt);initial=list(tokens)
    if len(tokens)>16:raise ValueError('The exact prompt exceeds the saved 16-token context; no truncation or refitting is performed.')
    import numpy as np
    generated=[]
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            for _ in range(count):
                scores=model.logits([tokens[-16:]])[0,-1]
                if not np.isfinite(scores).all():raise ValueError('Invalid imported-model inference scores.')
                token=int(np.argmax(scores));generated.append(token);tokens.append(token)
    except FloatingPointError as error:raise ValueError('Invalid imported-model inference scores.') from error
    return {'prompt':prompt,'prompt_token_ids':initial,'generated_token_ids':generated,'completion':codec.decode_preview(generated),'text':codec.decode_preview(tokens)}


def _verify(folder):
    envelope=json.loads((folder/'export-manifest.json').read_text(encoding='utf-8'));review=envelope['approved_review']
    if (envelope.get('format')!='almg-private-stream-decoder-export-v1' or type(envelope.get('schema_version')) is not int or envelope['schema_version']!=1
            or envelope.get('release_approved') is not False or review.get('format')!=envelope['format'] or review.get('release_approved') is not False
            or review.get('revision')!=digest({k:v for k,v in review.items() if k!='revision'})
            or review.get('files')!={name:file_digest(folder/name) for name in LIMITS if name!='export-manifest.json'}):raise ValueError('Streamed archive review or payload hashes changed.')
    model,codec,manifest=decoder_bundle.load(folder/'bundle')
    if manifest['stages']['tokenization']!=4 or manifest['training']['completed_steps']!=20:raise ValueError('Import requires the completed approved streamed training contract.')
    checkpoint=file_digest(folder/'bundle/manifest.json')
    evaluation=json.loads((folder/'evaluation.json').read_text(encoding='utf-8'));preview=json.loads((folder/'preview.json').read_text(encoding='utf-8'))
    for record,kind in ((evaluation,'almg-stream-cpu-evaluation-v1'),(preview,'almg-stream-training-preview-v1')):
        if (record.get('format')!=kind or type(record.get('schema_version')) is not int or record['schema_version']!=1
                or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                or record.get('run_id')!=review.get('run_id') or record.get('run_revision')!=review.get('run_revision')
                or record.get('checkpoint_manifest_sha256')!=checkpoint or record.get('tokenizer_sha256')!=codec.fingerprint()
                or record.get('release_approved') is not False or type(record.get('optimizer_updates')) is not int or record['optimizer_updates']!=0):raise ValueError('Streamed archive receipt binding changed.')
    if (review.get('checkpoint_manifest_sha256')!=checkpoint or review.get('evaluation_revision')!=evaluation['revision'] or review.get('preview_revision')!=preview['revision']
            or evaluation.get('passed') is not True or evaluation.get('target_next_token_accuracy')!=.8):raise ValueError('Streamed archive lacks its passing archived evaluation receipt.')
    if set(evaluation['evaluation'])!={'validation','test'}:raise ValueError('Streamed evaluation splits changed.')
    for metric in evaluation['evaluation'].values():
        if (type(metric.get('windows')) is not int or metric['windows']<=0 or type(metric.get('target_tokens')) is not int or metric['target_tokens']<=0
                or type(metric.get('correct_target_tokens')) is not int or not 0<=metric['correct_target_tokens']<=metric['target_tokens']
                or type(metric.get('loss')) not in (int,float) or not math.isfinite(metric['loss']) or metric['loss']<0
                or type(metric.get('next_token_accuracy')) not in (int,float) or not .8<=metric['next_token_accuracy']<=1
                or abs(metric['next_token_accuracy']-metric['correct_target_tokens']/metric['target_tokens'])>1e-12):raise ValueError('Invalid archived evaluation metrics.')
    repeated=_infer(folder,preview['prompt'],preview['inference']['max_new_tokens'])
    if any(preview.get(key)!=value for key,value in repeated.items()):raise ValueError('Archived preview does not reproduce against the imported weights/tokenizer.')
    return model,codec,manifest


def import_private(root,confirmed,source_name,encoded):
    if confirmed is not True:raise ValueError('Confirm isolated private streamed-model import; training and release are unavailable.')
    if not isinstance(source_name,str) or not 1<=len(source_name)<=255:raise ValueError('Provide a short archive name.')
    if not isinstance(encoded,str) or len(encoded)>12*1024*1024:raise ValueError('Streamed archives must fit 8 MiB.')
    try:
        data=base64.b64decode(encoded,validate=True)
        if not 0<len(data)<=8*1024*1024:raise ValueError('Streamed archives must fit 8 MiB.')
        training_resources.check_size(len(data),Path(root))
        contents={}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if len(entries)!=len(LIMITS) or {entry.filename for entry in entries}!=set(LIMITS):raise ValueError('Import requires exactly six versioned streamed archive members.')
            for entry in entries:
                if (entry.flag_bits&1 or entry.file_size>LIMITS[entry.filename] or entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)
                        or stat.S_IFMT(entry.external_attr>>16) not in (0,stat.S_IFREG)):raise ValueError('Unsupported, linked, encrypted or oversized archive entry.')
                with archive.open(entry) as stream:value=stream.read(LIMITS[entry.filename]+1)
                if len(value)!=entry.file_size or len(value)>LIMITS[entry.filename]:raise ValueError('Archive entry size changed.')
                contents[entry.filename]=value
        parent=Path(root)/'decoder-stream-training-imports';parent.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
        with TemporaryDirectory(prefix='.import-',dir=parent) as temporary:
            staged=Path(temporary)/identifier;(staged/'bundle').mkdir(parents=True)
            for name,value in contents.items():(staged/name).write_bytes(value)
            model,codec,_=_verify(staged)
            record={'format':FORMAT,'schema_version':1,'id':identifier,'source_name':source_name,'created_at':datetime.now(timezone.utc).isoformat(),
                    'archive_sha256':hashlib.sha256(data).hexdigest(),'files':{name:hashlib.sha256(value).hexdigest() for name,value in contents.items()},
                    'tokenizer_sha256':codec.fingerprint(),'config':model.config,'scope':'isolated_private_cpu_preview_only',
                    'evaluation_status':'archived_claims_not_re_evaluated_source_excluded','training_approved':False,'release_approved':False,'previews':[]}
            _write(staged,record);staged.rename(parent/identifier)
        return read(root,identifier)
    except (OSError,KeyError,TypeError,AttributeError,UnicodeError,zipfile.BadZipFile,RuntimeError) as error:raise ValueError('Streamed archive is invalid or incomplete.') from error


def _write(folder,record):
    record=dict(record);record['revision']=digest({k:v for k,v in record.items() if k!='revision'});temporary=folder/(uuid.uuid4().hex+'.tmp')
    serialized=json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2)
    if len(serialized.encode('utf-8'))>1024*1024:raise ValueError('Imported preview history exceeds its record limit; previous state retained.')
    try:
        temporary.write_text(serialized,encoding='utf-8');temporary.replace(folder/'import.json')
    finally:temporary.unlink(missing_ok=True)
    return record


def read(root,identifier):
    folder=_folder(root,identifier);path=folder/'import.json'
    if path.stat().st_size>1024*1024:raise ValueError('Imported state exceeds its record limit.')
    record=json.loads(path.read_text(encoding='utf-8'))
    if any((folder/name).stat().st_size>limit for name,limit in LIMITS.items()):raise ValueError('Imported payload exceeds its saved size limit.')
    if (record.get('format')!=FORMAT or type(record.get('schema_version')) is not int or record['schema_version']!=1 or record.get('id')!=identifier
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'}) or record.get('training_approved') is not False or record.get('release_approved') is not False
            or record.get('evaluation_status')!='archived_claims_not_re_evaluated_source_excluded' or record.get('scope')!='isolated_private_cpu_preview_only'
            or record.get('files')!={name:file_digest(folder/name) for name in LIMITS}):raise ValueError('Imported streamed-model integrity changed.')
    model,codec,_=_verify(folder)
    if codec.fingerprint()!=record['tokenizer_sha256'] or model.config!=record['config']:raise ValueError('Imported model/tokenizer configuration changed.')
    return record


def list_imports(root,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of private streamed imports.')
    parent=Path(root)/'decoder-stream-training-imports';records=[]
    for folder in parent.iterdir() if parent.exists() else []:
        if not re.fullmatch('[a-f0-9]{32}',folder.name):continue
        try:records.append(read(root,folder.name))
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(records,key=lambda record:record['created_at'],reverse=True)[:20]


def preview(root,identifier,confirmed,prompt,max_new_tokens=12):
    with _LOCK:return _preview(root,identifier,confirmed,prompt,max_new_tokens)


def _preview(root,identifier,confirmed,prompt,max_new_tokens=12):
    if confirmed is not True:raise ValueError('Confirm local CPU preview and saving the private prompt/output.')
    training_resources.check_size(65536,Path(root))
    record=read(root,identifier);result=_infer(_folder(root,identifier),prompt,max_new_tokens)
    if read(root,identifier)!=record:raise ValueError('Imported model changed during inference; no preview saved.')
    result.update(format='almg-private-stream-import-preview-v1',schema_version=1,id=uuid.uuid4().hex,import_id=identifier,
                  runtime='numpy_cpu',optimizer_updates=0,release_approved=False,
                  checkpoint_manifest_sha256=file_digest(_folder(root,identifier)/'bundle/manifest.json'),implementation_sha256=file_digest(Path(__file__)))
    updated=dict(record,previews=[*record['previews'][-4:],result]);_write(_folder(root,identifier),updated)
    return result
