"""Resumable full-index diagnostic scans; no source mutation or training admission."""
import json
import platform
import unicodedata
from pathlib import Path
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_datasets as datasets, decoder_stream_indexes as indexes
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_datasets as datasets
    import decoder_stream_indexes as indexes
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _folder(root,audit_id):
    # Reuse the established UUID validator without sharing the index namespace.
    indexes._folder(root,audit_id)
    return Path(root)/'decoder-stream-audits'/audit_id


def _runtime():
    return {'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version}


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_audits.py','decoder_datasets.py','decoder_stream_indexes.py')},'runtime':_runtime()})


def _state(connection):
    row=connection.execute('SELECT value FROM state WHERE id=1').fetchone()
    record=json.loads(row[0]) if row else {}
    if (record.get('format')!='almg-stream-index-audit-v1' or type(record.get('schema_version')) is not int
            or record['schema_version']!=1 or record.get('status') not in ('scanning','awaiting_publication')):
        raise ValueError('Unsupported full-index audit state.')
    return record


def begin(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm hygiene and contact-detail checks over the complete index.')
    index=indexes.read(root,index_id)
    if index['status']!='complete':raise ValueError('Complete text indexing before a full-index audit.')
    audit_id=uuid.uuid4().hex
    record={'format':'almg-stream-index-audit-v1','schema_version':1,'id':audit_id,'status':'scanning',
            'index_id':index_id,'index_revision':index['revision'],'index_file_sha256':index['files']['records.sqlite3'],
            'index_signature':indexes._signature(indexes._folder(root,index_id)/'records.sqlite3'),
            'source_id':index['source_id'],'source_name':index['source_name'],'source_sha256':index['source_sha256'],
            'total_records':index['unique_records'],'processed_records':0,'last_group':'','source_occurrences':0,
            'hygiene_review_records':0,'privacy_records':0,'privacy_matches':0,'privacy_match_occurrences':0,
            'score_cents_sum':0,'minimum_score':None,'maximum_score':None,'finding_records':0,
            'implementation_sha256':_implementation(),'runtime':_runtime(),
            'method':{'version':1,'population':'all_unique_normalized_records','quality':'text_hygiene_v1',
                      'review_below_score':80,'privacy':'local_contact_patterns_v1',
                      'maximum_detailed_contact_findings_per_record':20,'raw_text_included':False,
                      'limitations':'Heuristic hygiene/contact checks only; not comprehensive PII or contamination detection.'},
            'policy':'diagnostic_only_no_training_admission_change'}
    directory=_folder(root,audit_id);directory.mkdir(parents=True)
    with indexes._connect(directory/'audit.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE findings(group_sha256 TEXT PRIMARY KEY,split TEXT NOT NULL,value TEXT NOT NULL)')
        db.execute('CREATE INDEX findings_split ON findings(split,group_sha256)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def _publish(root,record):
    folder=_folder(root,record['id'])
    manifest={**record,'status':'complete',
              'average_score':round(record['score_cents_sum']/100/record['processed_records'],2) if record['processed_records'] else None,
              'files':{'audit.sqlite3':file_digest(folder/'audit.sqlite3')}}
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
        with indexes._connect(folder/'audit.sqlite3',True) as db:record=_state(db)
        if record['id']!=audit_id:raise ValueError('Full-index audit ID mismatch.')
        path=folder/'manifest.json'
        if path.exists():
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if (manifest.get('status')!='complete'
                    or {key:value for key,value in manifest.items() if key in record and key!='status'}!={key:value for key,value in record.items() if key!='status'}
                    or manifest.get('files')!={'audit.sqlite3':file_digest(folder/'audit.sqlite3')}
                    or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})):
                raise ValueError('Full-index audit integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Full-index audit is unavailable or incomplete.') from error


def list_audits(root,index_id):
    indexes.read(root,index_id)
    directory=Path(root)/'decoder-stream-audits';result=[]
    for folder in sorted(directory.iterdir()) if directory.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def step(root,audit_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm processing the full-index audit.')
    with _LOCK:
        record=read(root,audit_id)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Audit implementation changed; preserve progress and start a newly reviewed audit.')
        index_folder=indexes._folder(root,record['index_id']);database=index_folder/'records.sqlite3'
        manifest=json.loads((index_folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('revision')!=record['index_revision']
                or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})
                or indexes._signature(database)!=record['index_signature']):
            raise ValueError('The source index changed. Existing audit progress is preserved.')
        if record['status']=='awaiting_publication':return _publish(root,record)
        with indexes._connect(_folder(root,audit_id)/'audit.sqlite3') as db, indexes._connect(database,True) as source:
            db.execute('BEGIN IMMEDIATE');record=_state(db)
            cursor=source.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_group'],))
            processed=characters=0
            while processed<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=cursor.fetchone()
                if row is None:break
                group,text,split,line,offset,raw_sha,occurrences=row
                context={'name':f"{record['source_name']}:line {line}",'source_sha256':record['source_sha256'],'group':group,'split':split}
                privacy=datasets._privacy_findings(text,context);hygiene=datasets._text_hygiene(text,Tokenizer.words(text))
                reasons=(['low_text_hygiene'] if hygiene['score']<80 else [])+(['potential_personal_information'] if privacy else [])
                if reasons:
                    finding={**context,'first_line':line,'first_byte_offset':offset,'raw_line_sha256':raw_sha,
                             'occurrences':occurrences,'normalized_characters':len(text),'review_reasons':reasons,
                             'text_hygiene':hygiene,'privacy_matches':len(privacy),'privacy_findings':privacy[:20],
                             'privacy_findings_truncated':len(privacy)>20,'text_omitted':True,
                             'text_excerpt':'Original text omitted from audit; inspect the indexed source record.',
                             'excerpt_truncated':False}
                    db.execute('INSERT INTO findings VALUES(?,?,?)',(group,split,json.dumps(finding,ensure_ascii=False)))
                    record['finding_records']+=1
                record['processed_records']+=1;record['last_group']=group;record['source_occurrences']+=occurrences
                record['hygiene_review_records']+=int(hygiene['score']<80);record['privacy_records']+=int(bool(privacy))
                record['privacy_matches']+=len(privacy);record['privacy_match_occurrences']+=len(privacy)*occurrences
                score=hygiene['score'];record['score_cents_sum']+=round(score*100)
                record['minimum_score']=score if record['minimum_score'] is None else min(record['minimum_score'],score)
                record['maximum_score']=score if record['maximum_score'] is None else max(record['maximum_score'],score)
                processed+=1;characters+=len(text)
            more=source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_group'],)).fetchone()
            if more is None:
                if record['processed_records']!=record['total_records']:raise ValueError('Audit record totals do not match the approved index.')
                if indexes.read(root,record['index_id'])['revision']!=record['index_revision']:raise ValueError('Source index revision changed.')
                record['status']='awaiting_publication'
            db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return _publish(root,record) if record['status']=='awaiting_publication' else record


def record_page(root,audit_id,confirmed,cursor=None,split='all',limit=10):
    if confirmed is not True:raise ValueError('Confirm local audit finding review.')
    if type(limit) is not int or not 1<=limit<=20 or split not in ('all','train','validation','test'):raise ValueError('Choose a saved split and page size from 1 to 20.')
    record=read(root,audit_id)
    if record['status']!='complete':raise ValueError('Complete the audit before reviewing immutable findings.')
    after=''
    if cursor is not None:
        import re
        if (not isinstance(cursor,dict) or set(cursor)!={'revision','after','split'}
                or cursor.get('revision')!=record['revision'] or cursor.get('split')!=split
                or not isinstance(cursor.get('after'),str) or not re.fullmatch('[a-f0-9]{64}',cursor['after'])):
            raise ValueError('The audit cursor changed. Reopen the first page.')
        after=cursor['after']
    sql='SELECT value FROM findings WHERE group_sha256>?';parameters=[after]
    if split!='all':sql+=' AND split=?';parameters.append(split)
    sql+=' ORDER BY group_sha256 LIMIT ?';parameters.append(limit+1)
    with indexes._connect(_folder(root,audit_id)/'audit.sqlite3',True) as db:rows=db.execute(sql,parameters).fetchall()
    findings=[json.loads(row[0]) for row in rows[:limit]]
    return {'format':'almg-stream-audit-record-page-v1','schema_version':1,'audit_id':audit_id,
            'audit_revision':record['revision'],'split':split,'records':findings,'read_only':True,
            'next_cursor':{'revision':record['revision'],'after':findings[-1]['group'],'split':split} if len(rows)>limit else None}
