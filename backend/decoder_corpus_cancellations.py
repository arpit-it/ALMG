"""Source-bound cancellation intents for corpus continuation update boundaries."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
if __package__:
    from . import decoder_corpus_optimizer as training
else:
    import decoder_corpus_optimizer as training
_LOCK = threading.Lock()


def validate(identifier):
    training._folder(Path('.'), identifier)
    return identifier


def _path(root, identifier):
    return Path(root)/'decoder-corpus-cancellation-requests'/(validate(identifier)+'.json')


def _read(path):
    if path.stat().st_size > 16384:
        raise ValueError('Corpus cancellation receipt exceeds size limit.')
    record = json.loads(path.read_text())
    if ((record.get('format'),record.get('schema_version')) not in (('almg-corpus-cancellation-v1',1),('almg-corpus-cancellation-v2',2))
            or record.get('cancel_requested') is not True
            or record.get('revision') != training.digest({k:v for k,v in record.items() if k != 'revision'})):
        raise ValueError('Corpus cancellation receipt binding changed.')
    if (record['schema_version']==2 and record.get('source_kind') not in ('run','partial')) or (record['schema_version']==1 and record.get('source_kind','run')!='run'):
        raise ValueError('Invalid corpus cancellation source kind.')
    return record


def request(root, source_id, identifier, confirmed, source_kind='run'):
    if confirmed is not True:
        raise ValueError('Explicitly request cancellation of this corpus continuation.')
    path = _path(root, identifier)
    if source_kind=='run':
        parent=training.read(root,source_id)
    elif source_kind=='partial':
        if __package__:from .decoder_corpus_continuations import read
        else:from decoder_corpus_continuations import read
        parent=read(root,source_id)
        if parent.get('status')!='canceled':raise ValueError('Select a canceled corpus partial source.')
    else:raise ValueError('Unsupported corpus cancellation source kind.')
    with _LOCK:
        if path.exists():
            record = _read(path)
            if record['request_id'] != identifier or record['source_id'] != source_id or record['source_revision'] != parent['revision'] or record.get('source_kind','run')!=source_kind:
                raise ValueError('Corpus cancellation token belongs to another source.')
            return record
        record = {'format':'almg-corpus-cancellation-v2','schema_version':2,'request_id':identifier,
                  'source_id':source_id,'source_revision':parent['revision'],'source_kind':source_kind,'cancel_requested':True,
                  'created_at':datetime.now(timezone.utc).isoformat()}
        record['revision'] = training.digest(record); path.parent.mkdir(parents=True,exist_ok=True)
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.cancel-',delete=False) as output:
            json.dump(record,output,allow_nan=False); temporary=Path(output.name)
        temporary.replace(path)
        return record


def requested(root, source_id, source_revision, identifier, source_kind='run'):
    if identifier is None:
        return False
    path = _path(root, identifier)
    if not path.exists():
        return False
    record = _read(path)
    if record['request_id'] != identifier or record['source_id'] != source_id or record['source_revision'] != source_revision or record.get('source_kind','run')!=source_kind:
        raise ValueError('Corpus cancellation token/source binding changed.')
    return True
