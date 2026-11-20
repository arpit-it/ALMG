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
    if (record.get('format') != 'almg-corpus-cancellation-v1' or record.get('schema_version') != 1
            or record.get('cancel_requested') is not True
            or record.get('revision') != training.digest({k:v for k,v in record.items() if k != 'revision'})):
        raise ValueError('Corpus cancellation receipt binding changed.')
    return record


def request(root, source_id, identifier, confirmed):
    if confirmed is not True:
        raise ValueError('Explicitly request cancellation of this corpus continuation.')
    path = _path(root, identifier); parent = training.read(root, source_id)
    with _LOCK:
        if path.exists():
            record = _read(path)
            if record['request_id'] != identifier or record['source_id'] != source_id or record['source_revision'] != parent['revision']:
                raise ValueError('Corpus cancellation token belongs to another source.')
            return record
        record = {'format':'almg-corpus-cancellation-v1','schema_version':1,'request_id':identifier,
                  'source_id':source_id,'source_revision':parent['revision'],'cancel_requested':True,
                  'created_at':datetime.now(timezone.utc).isoformat()}
        record['revision'] = training.digest(record); path.parent.mkdir(parents=True,exist_ok=True)
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.cancel-',delete=False) as output:
            json.dump(record,output,allow_nan=False); temporary=Path(output.name)
        temporary.replace(path)
        return record


def requested(root, source_id, source_revision, identifier):
    if identifier is None:
        return False
    path = _path(root, identifier)
    if not path.exists():
        return False
    record = _read(path)
    if record['request_id'] != identifier or record['source_id'] != source_id or record['source_revision'] != source_revision:
        raise ValueError('Corpus cancellation token/source binding changed.')
    return True
