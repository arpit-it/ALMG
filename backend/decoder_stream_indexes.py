"""Transactional line-based text preparation with bounded buffers and SQLite state."""
import hashlib
from contextlib import contextmanager
import json
from pathlib import Path
import platform
import re
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_datasets as datasets
    from . import decoder_streams as streams
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_datasets as datasets
    import decoder_streams as streams
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest

_LOCK=threading.RLock()
MAX_LINE_BYTES=65536
MAX_STEP_BYTES=4*1024*1024
MAX_STEP_LINES=20000


def _folder(root,index_id):
    if not isinstance(index_id,str) or not re.fullmatch('[a-f0-9]{32}',index_id):
        raise ValueError('Invalid streamed text index ID.')
    return Path(root)/'decoder-stream-indexes'/index_id


def _implementation():
    return digest({name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_indexes.py','decoder_tokenizer.py','run_manifest.py')})


def _signature(path):
    stat=path.stat()
    return {'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino}


@contextmanager
def _connect(path,readonly=False):
    connection=sqlite3.connect(f'{path.as_uri()}?mode=ro' if readonly else str(path),uri=readonly,timeout=10)
    connection.execute('PRAGMA cache_size=-2048')
    connection.execute('PRAGMA temp_store=FILE')
    if not readonly:connection.execute('PRAGMA journal_mode=DELETE')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _state(connection):
    row=connection.execute('SELECT value FROM state WHERE id=1').fetchone()
    if row is None:raise ValueError('Streamed preparation state is unavailable.')
    record=json.loads(row[0])
    if record.get('format')!='almg-stream-text-index-v1' or type(record.get('schema_version')) is not int or record.get('schema_version')!=1:
        raise ValueError('Unsupported streamed preparation state.')
    return record


def begin(root,source_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm line-based preparation of the stored original source.')
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
            'method':{'version':1,'record_unit':'UTF-8 newline-delimited document',
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


def _publish(root,index_id,record):
    directory=_folder(root,index_id)
    with _connect(directory/'records.sqlite3',True) as connection:
        counts={part:0 for part in ('train','validation','test')}
        counts.update(dict(connection.execute('SELECT split,COUNT(*) FROM documents GROUP BY split')))
    manifest={**record,'status':'complete','split_counts':counts,
              'files':{'records.sqlite3':file_digest(directory/'records.sqlite3')},
              'findings':(['fewer_than_three_unique_records'] if record['unique_records']<3 else [])+
                         (['empty_evaluation_or_training_split'] if not all(counts.values()) else [])}
    manifest['revision']=digest(manifest)
    temporary=directory/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(directory/'manifest.json')
    finally:temporary.unlink(missing_ok=True)
    return manifest


def read(root,index_id):
    directory=_folder(root,index_id)
    try:
        with _connect(directory/'records.sqlite3',True) as connection:record=_state(connection)
        if record.get('id')!=index_id:raise ValueError('Streamed text index binding changed.')
        path=directory/'manifest.json'
        if path.exists():
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if (manifest.get('id')!=index_id or manifest.get('status')!='complete'
                    or {key:value for key,value in manifest.items() if key in record and key!='status'}!={key:value for key,value in record.items() if key!='status'}
                    or manifest.get('files')!={'records.sqlite3':file_digest(directory/'records.sqlite3')}
                    or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})):
                raise ValueError('Streamed text index integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Streamed text index is unavailable or incomplete.') from error


def list_indexes(root,source_id):
    streams.read(root,source_id)
    directory=Path(root)/'decoder-stream-indexes';result=[]
    for path in sorted(directory.iterdir()) if directory.exists() else []:
        if path.name.startswith('.'):continue
        try:
            record=read(root,path.name)
            if record['source_id']==source_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def step(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm processing the saved source index.')
    with _LOCK:
        record=read(root,index_id)
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
                        normalized=' '.join(Tokenizer.words(text)) if text.strip() else ''
                    except (ValueError,UnicodeError) as error:
                        raise ValueError(f'Invalid or unsupported UTF-8 text at byte {offset}; progress before this batch is preserved.') from error
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


def record_page(root,index_id,confirmed,cursor=None,split='all',limit=10):
    """Bounded read-only excerpts and current heuristic findings from an immutable index."""
    if confirmed is not True:raise ValueError('Confirm local indexed-record review.')
    if type(limit) is not int or not 1<=limit<=20 or split not in ('all','train','validation','test'):
        raise ValueError('Choose a saved split and a page size from 1 to 20.')
    manifest=read(root,index_id)
    if manifest['status']!='complete':raise ValueError('Complete text indexing before reviewing immutable records.')
    after=''
    if cursor is not None:
        if (not isinstance(cursor,dict) or set(cursor)!={'revision','after','split'}
                or cursor.get('revision')!=manifest['revision'] or cursor.get('split')!=split
                or not isinstance(cursor.get('after'),str) or not re.fullmatch('[a-f0-9]{64}',cursor['after'])):
            raise ValueError('The record cursor changed. Reopen the first page for this index and split.')
        after=cursor['after']
    sql='SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256>?'
    parameters=[after]
    if split!='all':sql+=' AND split=?';parameters.append(split)
    sql+=' ORDER BY group_sha256 LIMIT ?';parameters.append(limit+1)
    with _connect(_folder(root,index_id)/'records.sqlite3',True) as connection:
        rows=connection.execute(sql,parameters).fetchall()
    records=[]
    for group,text,part,line,offset,raw_sha,occurrences in rows[:limit]:
        source={'name':f"{manifest['source_name']}:line {line}",'source_sha256':manifest['source_sha256'],
                'group':group,'split':part}
        findings=datasets._privacy_findings(text,source)
        spans=[]
        for finding in sorted(findings,key=lambda item:item['normalized_character_start']):
            start,end=finding['normalized_character_start'],finding['normalized_character_end']
            if spans and start<spans[-1][1]:spans[-1]=(spans[-1][0],max(spans[-1][1],end))
            else:spans.append((start,end))
        pieces=[];position=0
        for start,end in spans:
            pieces.extend((text[position:start],'[CONTACT_REDACTED]'));position=end
        pieces.append(text[position:]);excerpt=''.join(pieces)
        records.append({**source,'first_line':line,'first_byte_offset':offset,'raw_line_sha256':raw_sha,
                        'occurrences':occurrences,'normalized_characters':len(text),
                        'text_excerpt':excerpt[:512],'excerpt_truncated':len(excerpt)>512,
                        'detected_contacts_masked':bool(findings),'privacy_matches':len(findings),
                        'privacy_findings':findings[:20],'privacy_findings_truncated':len(findings)>20,
                        'text_hygiene':datasets._text_hygiene(text,Tokenizer.words(text))})
    return {'format':'almg-stream-index-record-page-v1','schema_version':1,'index_id':index_id,
            'index_revision':manifest['revision'],'split':split,'page_size':limit,'records':records,
            'source_id':manifest['source_id'],'read_only':True,
            'analysis_method':{'version':1,'quality':'text_hygiene_v1','privacy':'local_contact_patterns_v1',
                               'maximum_excerpt_characters':512,'maximum_findings_per_record':20,'offsets':'original_normalized_text_unicode_codepoints',
                               'limitations':'Current local heuristics; other personal information may remain. No training gate changes.'},
            'analysis_implementation_sha256':digest({'index':file_digest(Path(__file__)),
                'heuristics':file_digest(Path(__file__).with_name('decoder_datasets.py'))}),
            'next_cursor':{'revision':manifest['revision'],'after':records[-1]['group'],'split':split}
                          if len(rows)>limit else None}
