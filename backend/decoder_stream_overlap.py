"""Resumable exhaustive pairwise shingle diagnostics with bounded record buffers."""
import json
import platform
import unicodedata
from pathlib import Path
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_indexes as indexes
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _folder(root,audit_id):
    # Reuse the established UUID validator without sharing the index namespace.
    indexes._folder(root,audit_id)
    return Path(root)/'decoder-stream-overlap'/audit_id


def _runtime():
    return {'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version}


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_overlap.py','decoder_tokenizer.py','decoder_stream_indexes.py')},'runtime':_runtime()})


def _state(connection):
    row=connection.execute('SELECT value FROM state WHERE id=1').fetchone()
    record=json.loads(row[0]) if row else {}
    if (record.get('format')!='almg-stream-overlap-v1' or type(record.get('schema_version')) is not int
            or record['schema_version']!=1 or record.get('status') not in ('scanning','awaiting_publication')):
        raise ValueError('Unsupported overlap report state.')
    return record


def begin(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm the exhaustive local record-pair overlap scan.')
    index=indexes.read(root,index_id)
    if index['status']!='complete':raise ValueError('Complete text indexing before a overlap report.')
    audit_id=uuid.uuid4().hex
    record={'format':'almg-stream-overlap-v1','schema_version':1,'id':audit_id,'status':'scanning',
            'index_id':index_id,'index_revision':index['revision'],'index_file_sha256':index['files']['records.sqlite3'],
            'index_signature':indexes._signature(indexes._folder(root,index_id)/'records.sqlite3'),
            'source_id':index['source_id'],'source_name':index['source_name'],'source_sha256':index['source_sha256'],
            'total_records':index['unique_records'],'total_pairs':index['unique_records']*(index['unique_records']-1)//2,
            'processed_pairs':0,'last_left':'','last_right':'','near_duplicate_pairs':0,'cross_split_pairs':0,'short_pairs_skipped':0,
            'implementation_sha256':_implementation(),'runtime':_runtime(),
            'method':{'version':1,'name':'word_shingle_jaccard','shingle_words':5,'minimum_words':12,'threshold':.8,
                      'population':'all_unordered_unique_record_pairs','raw_text_included':False,
                      'limitations':'Exhaustive quadratic comparison cost; lexical heuristic only, not comprehensive semantic contamination detection.'},
            'policy':'diagnostic_only_no_training_admission_change'}
    directory=_folder(root,audit_id);directory.mkdir(parents=True)
    with indexes._connect(directory/'overlap.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE findings(group_sha256 TEXT PRIMARY KEY,split TEXT NOT NULL,right_split TEXT NOT NULL,value TEXT NOT NULL)')
        db.execute('CREATE INDEX findings_split ON findings(split,group_sha256)')
        db.execute('CREATE INDEX findings_right_split ON findings(right_split,group_sha256)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def _publish(root,record):
    folder=_folder(root,record['id'])
    manifest={**record,'status':'complete','files':{'overlap.sqlite3':file_digest(folder/'overlap.sqlite3')}}
    manifest['revision']=digest(manifest)
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(folder/'manifest.json')
    finally:temporary.unlink(missing_ok=True)
    return manifest


def read(root,audit_id):
    folder=_folder(root,audit_id)
    try:
        with indexes._connect(folder/'overlap.sqlite3',True) as db:record=_state(db)
        if record['id']!=audit_id:raise ValueError('Overlap report ID mismatch.')
        path=folder/'manifest.json'
        if path.exists():
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if (manifest.get('status')!='complete'
                    or {key:value for key,value in manifest.items() if key in record and key!='status'}!={key:value for key,value in record.items() if key!='status'}
                    or manifest.get('files')!={'overlap.sqlite3':file_digest(folder/'overlap.sqlite3')}
                    or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})):
                raise ValueError('Overlap report integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Overlap report is unavailable or incomplete.') from error


def list_audits(root,index_id):
    indexes.read(root,index_id)
    directory=Path(root)/'decoder-stream-overlap';result=[]
    for folder in sorted(directory.iterdir()) if directory.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def _pairs(source,record):
    fields='group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences'.split(',')
    columns=','.join(f'{alias}.{field}' for alias in ('a','b') for field in fields)
    return source.execute(f'SELECT {columns} FROM documents a CROSS JOIN documents b '
                          'WHERE a.group_sha256>=? AND b.group_sha256>a.group_sha256 '
                          'AND (a.group_sha256>? OR b.group_sha256>?) '
                          'ORDER BY a.group_sha256,b.group_sha256 LIMIT 101',
                          (record['last_left'],record['last_left'],record['last_right']))


def step(root,audit_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm processing the overlap report.')
    with _LOCK:
        record=read(root,audit_id)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Overlap implementation changed; preserve progress and start a newly reviewed audit.')
        index_folder=indexes._folder(root,record['index_id']);database=index_folder/'records.sqlite3'
        manifest=json.loads((index_folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('revision')!=record['index_revision']
                or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})
                or indexes._signature(database)!=record['index_signature']):
            raise ValueError('The source index changed. Existing audit progress is preserved.')
        if record['status']=='awaiting_publication':return _publish(root,record)
        with indexes._connect(_folder(root,audit_id)/'overlap.sqlite3') as db, indexes._connect(database,True) as source:
            db.execute('BEGIN IMMEDIATE');record=_state(db)
            cursor=_pairs(source,record)
            processed=characters=0
            while processed<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=cursor.fetchone()
                if row is None:break
                left,right=row[:7],row[7:]
                left_group,left_text,left_split,left_line,left_offset,left_raw,left_occurrences=left
                right_group,right_text,right_split,right_line,right_offset,right_raw,right_occurrences=right
                words_left=Tokenizer.words(left_text);words_right=Tokenizer.words(right_text)
                if min(len(words_left),len(words_right))<12:
                    record['short_pairs_skipped']+=1
                else:
                    a={tuple(words_left[i:i+5]) for i in range(len(words_left)-4)}
                    b={tuple(words_right[i:i+5]) for i in range(len(words_right)-4)}
                    similarity=len(a&b)/len(a|b)
                    if similarity>=.8:
                        cross=left_split!=right_split
                        def reference(item):
                            group,text,split,line,offset,raw,occurrences=item
                            return {'group':group,'split':split,'first_line':line,'first_byte_offset':offset,
                                    'raw_line_sha256':raw,'occurrences':occurrences,
                                    'name':f"{record['source_name']}:line {line}",'source_sha256':record['source_sha256']}
                        finding={**reference(left),'pair_id':left_group+right_group,
                                 'records':[reference(left),reference(right)],'similarity':round(similarity,6),
                                 'cross_split':cross,'kind':'potential_evaluation_contamination' if cross else 'near_duplicate_records',
                                 'text_omitted':True,'text_excerpt':'Original texts omitted from overlap report.','excerpt_truncated':False}
                        db.execute('INSERT INTO findings VALUES(?,?,?,?)',(finding['pair_id'],left_split,right_split,json.dumps(finding,ensure_ascii=False)))
                        record['near_duplicate_pairs']+=1;record['cross_split_pairs']+=int(cross)
                record['processed_pairs']+=1;record['last_left']=left_group;record['last_right']=right_group
                processed+=1;characters+=len(left_text)+len(right_text)
            if _pairs(source,record).fetchone() is None:
                if record['processed_pairs']!=record['total_pairs']:raise ValueError('Pair totals do not match the approved index.')
                if indexes.read(root,record['index_id'])['revision']!=record['index_revision']:raise ValueError('Source index revision changed.')
                record['status']='awaiting_publication'
            db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return _publish(root,record) if record['status']=='awaiting_publication' else record


def record_page(root,audit_id,confirmed,cursor=None,split='all',limit=10):
    if confirmed is not True:raise ValueError('Confirm local overlap finding review.')
    if type(limit) is not int or not 1<=limit<=20 or split not in ('all','train','validation','test'):raise ValueError('Choose a saved split and page size from 1 to 20.')
    record=read(root,audit_id)
    if record['status']!='complete':raise ValueError('Complete the overlap scan before reviewing findings.')
    after=''
    if cursor is not None:
        import re
        if (not isinstance(cursor,dict) or set(cursor)!={'revision','after','split'}
                or cursor.get('revision')!=record['revision'] or cursor.get('split')!=split
                or not isinstance(cursor.get('after'),str) or not re.fullmatch('[a-f0-9]{128}',cursor['after'])):
            raise ValueError('The overlap cursor changed. Reopen the first page.')
        after=cursor['after']
    sql='SELECT value FROM findings WHERE group_sha256>?';parameters=[after]
    if split!='all':sql+=' AND (split=? OR right_split=?)';parameters.extend([split,split])
    sql+=' ORDER BY group_sha256 LIMIT ?';parameters.append(limit+1)
    with indexes._connect(_folder(root,audit_id)/'overlap.sqlite3',True) as db:rows=db.execute(sql,parameters).fetchall()
    findings=[json.loads(row[0]) for row in rows[:limit]]
    return {'format':'almg-stream-overlap-page-v1','schema_version':1,'audit_id':audit_id,
            'audit_revision':record['revision'],'split':split,'records':findings,'read_only':True,
            'next_cursor':{'revision':record['revision'],'after':findings[-1]['pair_id'],'split':split} if len(rows)>limit else None}
