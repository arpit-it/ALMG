"""Resumable strict text-only JSONL extraction into the shared streamed index contract."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_jsonl as jsonl,decoder_stream_indexes as indexes,decoder_streams as streams
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_jsonl as jsonl
    import decoder_stream_indexes as indexes
    import decoder_streams as streams
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_LINE_BYTES=indexes.MAX_LINE_BYTES
MAX_STEP_BYTES=indexes.MAX_STEP_BYTES
MAX_STEP_LINES=indexes.MAX_STEP_LINES
_folder=indexes._folder
_signature=indexes._signature
_connect=indexes._connect
_state=indexes._state
_publish=indexes._publish
read=indexes.read


def _implementation():
    return digest({name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_jsonl.py','decoder_jsonl.py','decoder_stream_indexes.py','decoder_tokenizer.py','run_manifest.py')})


def begin(root,source_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm text-only JSONL preparation of the stored original source.')
    source=streams.read(root,source_id)
    if source['status']!='stored_not_prepared':raise ValueError('Finish and verify source upload before text preparation.')
    original=streams.folder(root,source_id)/'source.bin'
    if file_digest(original)!=source['source_sha256']:raise ValueError('Stored original source hash mismatch.')
    index_id=uuid.uuid4().hex
    record={'format':'almg-stream-text-index-v1','schema_version':1,'id':index_id,
            'status':'indexing','source_id':source_id,'source_name':source['name'],
            'source_sha256':source['source_sha256'],'source_bytes':source['total_bytes'],
            'source_signature':_signature(original),'offset':0,'lines':0,'empty_lines':0,
            'unique_records':0,'duplicate_records':0,'implementation_sha256':_implementation(),
            'method':{'version':1,'record_unit':'JSONL text field per nonblank UTF-8 line','input_format':'jsonl_text_only_v1',
                      'unknown_and_duplicate_fields':'rejected','original_file_and_line_hashes_preserved':True,
                      'maximum_line_bytes':MAX_LINE_BYTES,'normalization':'NFC_whitespace_split_join',
                      'exact_deduplication':'normalized_sha256_keep_first_count_occurrences',
                      'split_policy':'normalized_hash_mod100_train80_validation10_test10'},
            'runtime':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version},
            'policy':'prepared_text_index_only_training_not_enabled'}
    directory=_folder(root,index_id);directory.mkdir(parents=True)
    with _connect(directory/'records.sqlite3') as connection:
        connection.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        connection.execute('CREATE TABLE documents(group_sha256 TEXT PRIMARY KEY,text TEXT NOT NULL,split TEXT NOT NULL,first_line INTEGER NOT NULL,first_byte_offset INTEGER NOT NULL,raw_line_sha256 TEXT NOT NULL,occurrences INTEGER NOT NULL)')
        connection.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def step(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm processing the saved source index.')
    with _LOCK:
        record=read(root,index_id)
        if record.get('method',{}).get('input_format')!='jsonl_text_only_v1':raise ValueError('This is not a JSONL text index.')
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():
            raise ValueError('Preparation implementation changed. Preserve this index and start a newly reviewed index.')
        original=streams.folder(root,record['source_id'])/'source.bin'
        if _signature(original)!=record['source_signature']:
            raise ValueError('Original source changed. Existing index progress is preserved; verify the original source.')
        directory=_folder(root,index_id)
        if record['status']=='awaiting_publication':return _publish(root,index_id,record)
        with _connect(directory/'records.sqlite3') as connection:
            connection.execute('BEGIN IMMEDIATE')
            record=_state(connection)
            initial=record['offset'];processed=0
            with original.open('rb') as source:
                source.seek(initial)
                while record['offset']<record['source_bytes'] and processed<MAX_STEP_LINES and record['offset']-initial<MAX_STEP_BYTES:
                    offset=source.tell();raw=source.readline(MAX_LINE_BYTES+1)
                    if not raw or len(raw)>MAX_LINE_BYTES:
                        raise ValueError(f'Line at byte {offset} exceeds 65536 bytes or source ended early. Progress before this batch is preserved.')
                    try:
                        text=raw.decode('utf-8')
                        if offset==0:text=text.removeprefix('\ufeff')
                        if any(ord(char)<32 and char not in '\r\n\t' for char in text):raise ValueError('control character')
                        if text.strip():
                            row=json.loads(text,object_pairs_hook=jsonl._object)
                            if not isinstance(row,dict):raise ValueError('Each JSONL line must be an object containing text.')
                            body=row['text'];body.encode('utf-8')
                            if not body.strip() or any(ord(char)<32 and char not in '\r\n\t' for char in body):
                                raise ValueError('JSONL text must be nonempty without unsupported control characters.')
                            normalized=' '.join(Tokenizer.words(body))
                        else:normalized=''
                    except (ValueError,UnicodeError,TypeError,RecursionError) as error:
                        raise ValueError(f'Invalid text-only JSONL at line {record["lines"]+1}, byte {offset}; progress before this batch is preserved. {error}') from error
                    record['lines']+=1;record['offset']=source.tell();processed+=1
                    if not normalized:
                        record['empty_lines']+=1;continue
                    group=digest(normalized);bucket=int(group[:8],16)%100
                    split='train' if bucket<80 else 'validation' if bucket<90 else 'test'
                    inserted=connection.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,1)',
                        (group,normalized,split,record['lines'],offset,hashlib.sha256(raw).hexdigest())).rowcount
                    if inserted:record['unique_records']+=1
                    else:
                        connection.execute('UPDATE documents SET occurrences=occurrences+1 WHERE group_sha256=?',(group,))
                        record['duplicate_records']+=1
            if record['offset']==record['source_bytes']:
                if file_digest(original)!=record['source_sha256']:raise ValueError('Original source hash changed; no index published.')
                record['status']='awaiting_publication'
            connection.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return _publish(root,index_id,record) if record['status']=='awaiting_publication' else record
