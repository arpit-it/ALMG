"""Resumable bounded-chunk source storage, separate from prepared training datasets."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import threading
import uuid

if __package__:
    from .run_manifest import file_digest
else:
    from run_manifest import file_digest

_LOCK = threading.RLock()
CHUNK_BYTES = 65536
MAX_SOURCE_BYTES = 1024 ** 4


def folder(root, source_id):
    if not isinstance(source_id,str) or not re.fullmatch('[a-f0-9]{32}',source_id):
        raise ValueError('Invalid streamed source ID.')
    return Path(root)/'decoder-streams'/source_id


def _write(path, record):
    temporary=path/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path/'record.json')
    finally:
        temporary.unlink(missing_ok=True)


def _load(root, source_id):
    path=folder(root,source_id)
    try:
        record=json.loads((path/'record.json').read_text(encoding='utf-8'))
        if (record.get('format')!='almg-streamed-source-v1' or type(record.get('schema_version')) is not int
                or record['schema_version']!=1 or record.get('id')!=source_id
                or record.get('status') not in ('uploading','stored_not_prepared')
                or type(record.get('total_bytes')) is not int or not 1<=record['total_bytes']<=MAX_SOURCE_BYTES
                or type(record.get('received_bytes')) is not int or not 0<=record['received_bytes']<=record['total_bytes']
                or not isinstance(record.get('source_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',record['source_sha256'])):
            raise ValueError('Invalid streamed source record.')
        size=(path/'source.bin').stat().st_size
        if size<record['received_bytes']:
            raise ValueError('Saved source is shorter than its committed upload offset.')
        if size>record['received_bytes']:
            if record['status']!='uploading':
                raise ValueError('Stored source size changed.')
            # An interrupted record write may leave an uncommitted tail. Only
            # bytes beyond the durable offset are discarded; committed bytes stay.
            with (path/'source.bin').open('r+b') as stream:
                stream.truncate(record['received_bytes'])
                stream.flush();os.fsync(stream.fileno())
        return record
    except (OSError,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Streamed source is unavailable or incomplete.') from error


def create(root, name, total_bytes, source_sha256, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm storing the selected original source locally.')
    if not isinstance(name,str) or not 1<=len(name)<=255:
        raise ValueError('Provide a source filename.')
    if type(total_bytes) is not int or not 1<=total_bytes<=MAX_SOURCE_BYTES:
        raise ValueError('Select a nonempty source of at most 1 TiB.')
    if not isinstance(source_sha256,str) or not re.fullmatch('[a-f0-9]{64}',source_sha256):
        raise ValueError('Hash the selected source before upload.')
    source_id=uuid.uuid4().hex
    record={'format':'almg-streamed-source-v1','schema_version':1,'id':source_id,'name':name,
            'total_bytes':total_bytes,'received_bytes':0,'source_sha256':source_sha256,
            'chunk_bytes':CHUNK_BYTES,'status':'uploading','policy':'local_source_storage_only_no_training',
            'text_validation':'not_prepared_or_validated_as_utf8'}
    directory=Path(root)/'decoder-streams';directory.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.upload-',dir=directory) as temporary:
        staged=Path(temporary)/'source';staged.mkdir()
        (staged/'source.bin').touch();_write(staged,record)
        staged.rename(directory/source_id)
    return record


def read(root, source_id):
    with _LOCK:
        return _load(root,source_id)


def list_sources(root):
    directory=Path(root)/'decoder-streams';result=[]
    for path in sorted(directory.iterdir()) if directory.exists() else []:
        if path.name.startswith('.'):continue
        try:result.append(read(root,path.name))
        except ValueError:continue
    return result[-20:]


def append(root, source_id, offset, encoded, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm this local source upload chunk.')
    if type(offset) is not int or offset<0 or not isinstance(encoded,str) or not 1<=len(encoded)<=90000:
        raise ValueError('Provide a bounded upload chunk and exact byte offset.')
    data=base64.b64decode(encoded,validate=True)
    if not 1<=len(data)<=CHUNK_BYTES:
        raise ValueError('Upload chunks must contain 1 to 65536 bytes.')
    with _LOCK:
        record=_load(root,source_id);path=folder(root,source_id)
        if record['status']!='uploading':
            raise ValueError('This source is already stored; no further writes are allowed.')
        if offset<record['received_bytes'] and offset+len(data)<=record['received_bytes']:
            with (path/'source.bin').open('rb') as stream:
                stream.seek(offset)
                if stream.read(len(data))==data:return record
            raise ValueError('Retried chunk does not match committed source bytes.')
        if offset!=record['received_bytes'] or offset+len(data)>record['total_bytes']:
            raise ValueError('Upload offset changed. Reopen the saved source and resume its committed offset.')
        with (path/'source.bin').open('r+b') as stream:
            stream.seek(offset);stream.write(data);stream.flush();os.fsync(stream.fileno())
        record['received_bytes']+=len(data)
        _write(path,record)
        return record


def seal(root, source_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm verification of the uploaded original source.')
    with _LOCK:
        record=_load(root,source_id)
        if record['received_bytes']!=record['total_bytes']:
            raise ValueError('Upload the remaining bytes before verifying the source.')
        if file_digest(folder(root,source_id)/'source.bin')!=record['source_sha256']:
            raise ValueError('Original source hash mismatch. Preserve this upload and select the original file for a new session.')
        if record['status']=='uploading':
            record['status']='stored_not_prepared';_write(folder(root,source_id),record)
        return record
