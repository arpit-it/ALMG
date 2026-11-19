"""Resumable optional dominant-language reports; no source mutation or training admission."""
import json
import platform
import unicodedata
from pathlib import Path
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_languages as languages, decoder_stream_indexes as indexes
    from .run_manifest import digest,file_digest
else:
    import decoder_languages as languages
    import decoder_stream_indexes as indexes
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _folder(root,audit_id):
    # Reuse the established UUID validator without sharing the index namespace.
    indexes._folder(root,audit_id)
    return Path(root)/'decoder-stream-languages'/audit_id


def _runtime():
    return {'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version,
            'system':platform.system(),'macos_version':platform.mac_ver()[0],'machine':platform.machine()}


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_languages.py','decoder_languages.py','local_language.js','decoder_stream_indexes.py')},'runtime':_runtime()})


def _state(connection):
    row=connection.execute('SELECT value FROM state WHERE id=1').fetchone()
    record=json.loads(row[0]) if row else {}
    if (record.get('format')!='almg-stream-index-languages-v1' or type(record.get('schema_version')) is not int
            or record['schema_version']!=1 or record.get('status') not in ('scanning','awaiting_publication')):
        raise ValueError('Unsupported language report state.')
    return record


def begin(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm optional local language identification over the complete index.')
    index=indexes.read(root,index_id)
    if index['status']!='complete':raise ValueError('Complete text indexing before a language report.')
    audit_id=uuid.uuid4().hex
    record={'format':'almg-stream-index-languages-v1','schema_version':1,'id':audit_id,'status':'scanning',
            'index_id':index_id,'index_revision':index['revision'],'index_file_sha256':index['files']['records.sqlite3'],
            'index_signature':indexes._signature(indexes._folder(root,index_id)/'records.sqlite3'),
            'source_id':index['source_id'],'source_name':index['source_name'],'source_sha256':index['source_sha256'],
            'total_records':index['unique_records'],'processed_records':0,'last_group':'','source_occurrences':0,
            'identified_records':0,'unknown_records':0,'unavailable_batches':0,
            'language_counts':{},'split_language_counts':{part:{} for part in ('train','validation','test')},
            'implementation_sha256':_implementation(),'runtime':_runtime(),
            'method':{'version':1,'provider':'apple_natural_language_optional','minimum_alphabetic_characters':40,
                      'minimum_confidence':.8,'minimum_margin':.2,'maximum_candidates':3,
                      'granularity':'dominant_language_per_unique_normalized_record','raw_text_included':False,
                      'limitations':'Probabilistic estimate; short, mixed or unsupported text can be unknown. No filtering or training approval.'},
            'policy':'diagnostic_only_no_training_admission_change'}
    directory=_folder(root,audit_id);directory.mkdir(parents=True)
    with indexes._connect(directory/'languages.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE findings(group_sha256 TEXT PRIMARY KEY,split TEXT NOT NULL,value TEXT NOT NULL)')
        db.execute('CREATE INDEX findings_split ON findings(split,group_sha256)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def _publish(root,record):
    folder=_folder(root,record['id'])
    manifest={**record,'status':'complete','files':{'languages.sqlite3':file_digest(folder/'languages.sqlite3')}}
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
        with indexes._connect(folder/'languages.sqlite3',True) as db:record=_state(db)
        if record['id']!=audit_id:raise ValueError('Language report ID mismatch.')
        path=folder/'manifest.json'
        if path.exists():
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if (manifest.get('status')!='complete'
                    or {key:value for key,value in manifest.items() if key in record and key!='status'}!={key:value for key,value in record.items() if key!='status'}
                    or manifest.get('files')!={'languages.sqlite3':file_digest(folder/'languages.sqlite3')}
                    or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})):
                raise ValueError('Language report integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Language report is unavailable or incomplete.') from error


def list_audits(root,index_id):
    indexes.read(root,index_id)
    directory=Path(root)/'decoder-stream-languages';result=[]
    for folder in sorted(directory.iterdir()) if directory.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def step(root,audit_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm processing the language report.')
    with _LOCK:
        record=read(root,audit_id)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Language implementation changed; preserve progress and start a newly reviewed audit.')
        index_folder=indexes._folder(root,record['index_id']);database=index_folder/'records.sqlite3'
        manifest=json.loads((index_folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('revision')!=record['index_revision']
                or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})
                or indexes._signature(database)!=record['index_signature']):
            raise ValueError('The source index changed. Existing audit progress is preserved.')
        if record['status']=='awaiting_publication':return _publish(root,record)
        with indexes._connect(_folder(root,audit_id)/'languages.sqlite3') as db, indexes._connect(database,True) as source:
            db.execute('BEGIN IMMEDIATE');record=_state(db)
            cursor=source.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_group'],))
            batch=[];characters=0
            while len(batch)<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=cursor.fetchone()
                if row is None:break
                batch.append(row);characters+=len(row[1])
            eligible=[i for i,row in enumerate(batch) if sum(char.isalpha() for char in row[1])>=40]
            predictions=languages._recognize([batch[i][1] for i in eligible]) if eligible else []
            by_index=dict(zip(eligible,predictions)) if predictions is not None else {}
            record['unavailable_batches']+=int(predictions is None)
            for i,(group,text,split,line,offset,raw_sha,occurrences) in enumerate(batch):
                candidates=sorted(by_index.get(i,{}).items(),key=lambda item:(-item[1],item[0]))
                confidence=candidates[0][1] if candidates else 0.0
                margin=confidence-(candidates[1][1] if len(candidates)>1 else 0.0)
                identified=bool(candidates) and candidates[0][0]!='und' and confidence>=.8 and margin>=.2
                reason='insufficient_alphabetic_text' if i not in eligible else 'provider_unavailable' if predictions is None else 'ambiguous_or_unrecognized'
                language=candidates[0][0] if identified else 'und'
                finding={'name':f"{record['source_name']}:line {line}",'source_sha256':record['source_sha256'],
                         'group':group,'split':split,'first_line':line,'first_byte_offset':offset,
                         'raw_line_sha256':raw_sha,'occurrences':occurrences,
                         'status':'identified' if identified else 'unknown','language':language,
                         'confidence':round(confidence,6),'reason':'confidence_and_margin_met' if identified else reason,
                         'candidates':[{'language':code,'confidence':round(value,6)} for code,value in candidates],
                         'text_omitted':True,'text_excerpt':'Original text omitted from language report.','excerpt_truncated':False}
                db.execute('INSERT INTO findings VALUES(?,?,?)',(group,split,json.dumps(finding,ensure_ascii=False)))
                record['processed_records']+=1;record['last_group']=group;record['source_occurrences']+=occurrences
                record['identified_records']+=int(identified);record['unknown_records']+=int(not identified)
                for counts in (record['language_counts'],record['split_language_counts'][split]):
                    counts[language]=counts.get(language,0)+1
            more=source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_group'],)).fetchone()
            if more is None:
                if record['processed_records']!=record['total_records']:raise ValueError('Language record totals do not match the approved index.')
                if indexes.read(root,record['index_id'])['revision']!=record['index_revision']:raise ValueError('Source index revision changed.')
                record['status']='awaiting_publication'
            db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return _publish(root,record) if record['status']=='awaiting_publication' else record


def record_page(root,audit_id,confirmed,cursor=None,split='all',limit=10):
    if confirmed is not True:raise ValueError('Confirm local language-record review.')
    if type(limit) is not int or not 1<=limit<=20 or split not in ('all','train','validation','test'):raise ValueError('Choose a saved split and page size from 1 to 20.')
    record=read(root,audit_id)
    if record['status']!='complete':raise ValueError('Complete the language report before reviewing records.')
    after=''
    if cursor is not None:
        import re
        if (not isinstance(cursor,dict) or set(cursor)!={'revision','after','split'}
                or cursor.get('revision')!=record['revision'] or cursor.get('split')!=split
                or not isinstance(cursor.get('after'),str) or not re.fullmatch('[a-f0-9]{64}',cursor['after'])):
            raise ValueError('The language cursor changed. Reopen the first page.')
        after=cursor['after']
    sql='SELECT value FROM findings WHERE group_sha256>?';parameters=[after]
    if split!='all':sql+=' AND split=?';parameters.append(split)
    sql+=' ORDER BY group_sha256 LIMIT ?';parameters.append(limit+1)
    with indexes._connect(_folder(root,audit_id)/'languages.sqlite3',True) as db:rows=db.execute(sql,parameters).fetchall()
    findings=[json.loads(row[0]) for row in rows[:limit]]
    return {'format':'almg-stream-language-record-page-v1','schema_version':1,'audit_id':audit_id,
            'audit_revision':record['revision'],'split':split,'records':findings,'read_only':True,
            'next_cursor':{'revision':record['revision'],'after':findings[-1]['group'],'split':split} if len(rows)>limit else None}
