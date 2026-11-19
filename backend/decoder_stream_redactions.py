"""Transactional contact-pattern filtering into a new immutable streamed index."""
import json
import platform
import sqlite3
import unicodedata
from pathlib import Path
import threading
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_datasets as datasets, decoder_stream_permissions as permissions
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_datasets as datasets
    import decoder_stream_permissions as permissions
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _implementation():
    return digest({'code':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_redactions.py','decoder_datasets.py','decoder_tokenizer.py','decoder_stream_indexes.py')},
                   'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version})


def begin(root,index_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm a new contact-filtered index; the original remains unchanged.')
    parent=indexes.read(root,index_id)
    if parent['status']!='complete':raise ValueError('Complete the parent index before filtering.')
    if not isinstance(reviewed,dict) or reviewed!=parent:raise ValueError('The parent index review changed. Reopen it before filtering.')
    if parent.get('derivation',{}).get('operation')=='contact_pattern_filter':raise ValueError('This version is already contact-filtered; review its remaining findings instead.')
    permission_review=permissions.review(root,index_id)
    record={key:value for key,value in parent.items() if key not in ('files','revision','findings','split_counts')}
    record.update(id=uuid.uuid4().hex,status='redacting',unique_records=0,offset=0,
                  processed_parent_records=0,total_parent_records=parent['unique_records'],last_parent_group='',
                  filtered_records=0,replacement_spans=0,implementation_sha256=_implementation(),
                  parent_signature=indexes._signature(indexes._folder(root,index_id)/'records.sqlite3'),
                  derivation={'version':1,'operation':'contact_pattern_filter','parent_index_id':index_id,
                              'parent_index_revision':parent['revision'],'parent_source_permission_review':permission_review,
                              'marker':'[CONTACT_REDACTED]','lineage_table':'redaction_lineage',
                              'policy':'current_contact_patterns_only_fresh_splits_new_review_no_approval_transfer'},
                  method={**parent['method'],'preprocessing':'contact_pattern_filter_v1',
                          'limitations':'Current local contact heuristics only; other personal information may remain.'})
    folder=indexes._folder(root,record['id']);folder.mkdir(parents=True)
    with indexes._connect(folder/'records.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE documents(group_sha256 TEXT PRIMARY KEY,text TEXT NOT NULL,split TEXT NOT NULL,first_line INTEGER NOT NULL,first_byte_offset INTEGER NOT NULL,raw_line_sha256 TEXT NOT NULL,occurrences INTEGER NOT NULL)')
        db.execute('CREATE TABLE redaction_lineage(parent_group TEXT PRIMARY KEY,derived_group TEXT NOT NULL,parent_split TEXT NOT NULL,first_line INTEGER NOT NULL,first_byte_offset INTEGER NOT NULL,raw_line_sha256 TEXT NOT NULL,occurrences INTEGER NOT NULL,replacement_spans INTEGER NOT NULL)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def step(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing contact filtering.')
    with _LOCK:
        record=indexes.read(root,index_id)
        if record['status']=='complete':return record
        derivation=record.get('derivation',{})
        if derivation.get('operation')!='contact_pattern_filter':raise ValueError('This index is not a contact-filter preparation.')
        if record['implementation_sha256']!=_implementation():raise ValueError('Filtering implementation changed; preserve this index and start a new reviewed version.')
        parent_id=derivation['parent_index_id'];folder=indexes._folder(root,index_id)
        parent_folder=indexes._folder(root,parent_id);parent_database=parent_folder/'records.sqlite3'
        manifest=json.loads((parent_folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('revision')!=derivation['parent_index_revision']
                or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})
                or indexes._signature(parent_database)!=record['parent_signature']):
            raise ValueError('Parent index changed. Committed filtering progress is preserved.')
        if record['status']=='awaiting_publication':return indexes._publish(root,index_id,record)
        with indexes._connect(folder/'records.sqlite3') as db,indexes._connect(parent_database,True) as source:
            db.execute('BEGIN IMMEDIATE');record=indexes._state(db)
            cursor=source.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_parent_group'],))
            processed=characters=0
            while processed<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=cursor.fetchone()
                if row is None:break
                group,text,old_split,line,offset,raw_sha,occurrences=row
                context={'name':f"{record['source_name']}:line {line}",'source_sha256':record['source_sha256'],'group':group,'split':old_split}
                findings=datasets._privacy_findings(text,context);spans=[]
                for finding in sorted(findings,key=lambda item:item['normalized_character_start']):
                    start,end=finding['normalized_character_start'],finding['normalized_character_end']
                    if spans and start<spans[-1][1]:spans[-1]=(spans[-1][0],max(spans[-1][1],end))
                    else:spans.append((start,end))
                filtered=text
                for start,end in reversed(spans):filtered=filtered[:start]+'[CONTACT_REDACTED]'+filtered[end:]
                filtered=' '.join(Tokenizer.words(filtered));derived=digest(filtered);bucket=int(derived[:8],16)%100
                split='train' if bucket<80 else 'validation' if bucket<90 else 'test'
                inserted=db.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?)',(derived,filtered,split,line,offset,raw_sha,occurrences)).rowcount
                if inserted:record['unique_records']+=1
                else:
                    db.execute('UPDATE documents SET occurrences=occurrences+? WHERE group_sha256=?',(occurrences,derived))
                    db.execute('UPDATE documents SET first_line=?,first_byte_offset=?,raw_line_sha256=? WHERE group_sha256=? AND first_line>?',(line,offset,raw_sha,derived,line))
                    record['duplicate_records']+=1
                db.execute('INSERT INTO redaction_lineage VALUES(?,?,?,?,?,?,?,?)',(group,derived,old_split,line,offset,raw_sha,occurrences,len(spans)))
                record['processed_parent_records']+=1;record['last_parent_group']=group
                record['filtered_records']+=int(bool(spans));record['replacement_spans']+=len(spans)
                processed+=1;characters+=len(text)
            if source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_parent_group'],)).fetchone() is None:
                if record['processed_parent_records']!=record['total_parent_records']:raise ValueError('Filtering record totals do not match the parent index.')
                if indexes.read(root,parent_id)['revision']!=derivation['parent_index_revision']:raise ValueError('Parent index revision changed.')
                record['offset']=record['source_bytes'];record['status']='awaiting_publication'
            db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return indexes._publish(root,index_id,record) if record['status']=='awaiting_publication' else record
