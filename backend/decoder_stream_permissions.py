"""Immutable user declarations for streamed-index source bytes; no approval grant."""
import json
from pathlib import Path
import threading
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_datasets as datasets
    from .run_manifest import digest
else:
    import decoder_stream_indexes as indexes
    import decoder_datasets as datasets
    from run_manifest import digest

_LOCK=threading.RLock()
MAX_DECLARATIONS=32


def snapshot(root,manifest):
    index_id=manifest['id'];indexes._folder(root,index_id)
    folder=Path(root)/'decoder-stream-permissions'/index_id
    paths=sorted(folder.glob('[0-9][0-9][0-9][0-9].json')) if folder.exists() else []
    if len(paths)>MAX_DECLARATIONS:raise ValueError('Source declaration history exceeds the supported bound.')
    history=[];previous=None
    for sequence,path in enumerate(paths,1):
        if path.name!=f'{sequence:04}.json':raise ValueError('Source declaration sequence is incomplete.')
        try:
            if path.stat().st_size>16384:raise ValueError('Source declaration exceeds the supported size.')
            record=json.loads(path.read_text(encoding='utf-8'))
            if (record.get('format')!='almg-stream-source-permission-v1' or type(record.get('schema_version')) is not int
                    or record['schema_version']!=1 or record.get('sequence')!=sequence
                    or record.get('index_id')!=index_id or record.get('index_revision')!=manifest['revision']
                    or record.get('source_sha256')!=manifest['source_sha256']
                    or record.get('previous_revision')!=previous or record.get('basis') not in datasets.LICENSE_BASES
                    or not isinstance(record.get('note'),str) or not 1<=len(record['note'].strip())<=1000
                    or record.get('user_declared') is not True or record.get('permission_verified') is not False
                    or record.get('training_approved') is not False
                    or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):
                raise ValueError('Source declaration integrity check failed.')
        except (OSError,TypeError,KeyError) as error:raise ValueError('Source declaration is unavailable.') from error
        history.append(record);previous=record['revision']
    result={'format':'almg-stream-source-permission-review-v1','schema_version':1,
            'index_id':index_id,'index_revision':manifest['revision'],
            'source_provenance':{key:manifest[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
            'declarations':history,'latest_declaration':history[-1] if history else None,
            'permission_verified':False,'training_approved':False}
    result['revision']=digest(result)
    return result


def review(root,index_id):
    manifest=indexes.read(root,index_id)
    if manifest['status']!='complete':raise ValueError('Complete text indexing before source declarations.')
    return snapshot(root,manifest)


def declare(root,index_id,confirmed,reviewed,basis,note):
    if confirmed is not True:raise ValueError('Confirm the exact source declaration and note.')
    if not isinstance(basis,str) or basis not in datasets.LICENSE_BASES:raise ValueError('Choose a supported user-declared source basis.')
    if not isinstance(note,str) or not 1<=len(note.strip())<=1000:raise ValueError('Provide a source note of 1 to 1000 characters.')
    with _LOCK:
        current=review(root,index_id)
        if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('The source review changed. Reopen it before declaring.')
        if len(current['declarations'])>=MAX_DECLARATIONS:raise ValueError('Source declaration history is full; existing declarations are preserved.')
        latest=current['latest_declaration']
        if latest and latest['basis']==basis and latest['note']==note.strip():raise ValueError('This source declaration is already recorded.')
        record={'format':'almg-stream-source-permission-v1','schema_version':1,
                'sequence':len(current['declarations'])+1,'index_id':index_id,'index_revision':current['index_revision'],
                'source_sha256':current['source_provenance']['source_sha256'],
                'previous_revision':latest['revision'] if latest else None,
                'basis':basis,'note':note.strip(),'user_declared':True,'permission_verified':False,'training_approved':False}
        record['revision']=digest(record)
        folder=Path(root)/'decoder-stream-permissions'/index_id;folder.mkdir(parents=True,exist_ok=True)
        temporary=folder/(uuid.uuid4().hex+'.tmp');destination=folder/f"{record['sequence']:04}.json"
        try:
            temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            if destination.exists():raise ValueError('Source declaration sequence changed.')
            temporary.rename(destination)
        finally:temporary.unlink(missing_ok=True)
        return review(root,index_id)
