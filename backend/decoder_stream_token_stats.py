"""Resumable fixed-byte alphabet diagnostics; no tokenizer fitting or training."""
from collections import Counter
import json
from pathlib import Path
import platform
import threading
import unicodedata
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_indexes as indexes
    from run_manifest import digest, file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _folder(root,report_id):
    indexes._folder(root,report_id)
    return Path(root)/'decoder-stream-token-stats'/report_id


def _implementation():
    return digest({'code':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_token_stats.py','decoder_tokenizer.py')},
                   'python':platform.python_version(),'unicode':unicodedata.unidata_version})


def _save(root,record):
    folder=_folder(root,record['id']);folder.mkdir(parents=True,exist_ok=True)
    record={k:v for k,v in record.items() if k!='revision'}
    record['revision']=digest(record)
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        temporary.replace(folder/'report.json')
    finally:temporary.unlink(missing_ok=True)
    return record


def read(root,report_id):
    try:
        record=json.loads((_folder(root,report_id)/'report.json').read_text(encoding='utf-8'))
        if (record.get('format')!='almg-stream-byte-statistics-v1' or type(record.get('schema_version')) is not int
                or record['schema_version']!=1 or record.get('id')!=report_id
                or record.get('status') not in ('scanning','complete')
                or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):
            raise ValueError('Byte-statistics report integrity check failed.')
        return record
    except (OSError,TypeError,KeyError) as error:
        raise ValueError('Byte-statistics report is unavailable.') from error


def begin(root,index_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm the local fixed-byte token distribution scan.')
    index=indexes.read(root,index_id)
    if index['status']!='complete':raise ValueError('Complete text indexing before byte statistics.')
    return _save(root,{'format':'almg-stream-byte-statistics-v1','schema_version':1,'id':uuid.uuid4().hex,
        'status':'scanning','index_id':index_id,'index_revision':index['revision'],
        'index_signature':indexes._signature(indexes._folder(root,index_id)/'records.sqlite3'),
        'source_provenance':{key:index[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
        'implementation_sha256':_implementation(),'total_records':index['unique_records'],
        'processed_records':0,'last_group':'',
        'method':{'version':1,'alphabet':'almg-utf8-byte-tokenizer-v1','normalization':'NFC',
                  'token_ids':'0..255; each ID equals its UTF-8 byte value','vocabulary_size':256,
                  'special_tokens_included':False,'raw_text_included':False,'tokenizer_fitted':False,
                  'current_tokenizer_maximum_document_bytes':4096,
                  'limitations':'Byte-alphabet diagnostics only; no saved tokenizer, word/BPE analysis or training admission.'},
        'splits':{split:{'unique_records':0,'source_occurrences':0,'characters':0,'tokens':0,
                        'occurrence_weighted_tokens':0,'minimum_record_tokens':None,'maximum_record_tokens':0,
                        'records_over_current_tokenizer_limit':0,'token_counts':[0]*256,
                        'occurrence_weighted_token_counts':[0]*256} for split in ('train','validation','test')},
        'training_approved':False})


def list_reports(root,index_id):
    indexes.read(root,index_id)
    folder=Path(root)/'decoder-stream-token-stats';reports=[]
    for path in sorted(folder.iterdir()) if folder.exists() else []:
        if path.name.startswith('.'):continue
        try:
            record=read(root,path.name)
            if record['index_id']==index_id:reports.append(record)
        except ValueError:continue
    return reports[-20:]


def step(root,report_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing byte statistics.')
    with _LOCK:
        record=read(root,report_id)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Byte analysis implementation changed; preserve this report and start a new reviewed scan.')
        folder=indexes._folder(root,record['index_id']);database=folder/'records.sqlite3'
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('revision')!=record['index_revision']
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or indexes._signature(database)!=record['index_signature']):
            raise ValueError('The source index changed; saved report progress is preserved.')
        with indexes._connect(database,True) as source:
            rows=source.execute('SELECT group_sha256,text,split,occurrences FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_group'],))
            processed=characters=0
            while processed<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=rows.fetchone()
                if row is None:break
                group,text,split,occurrences=row
                encoded=unicodedata.normalize('NFC',text).encode('utf-8');counts=Counter(encoded)
                stats=record['splits'][split];length=len(encoded)
                stats['unique_records']+=1;stats['source_occurrences']+=occurrences
                stats['characters']+=len(text);stats['tokens']+=length
                stats['occurrence_weighted_tokens']+=length*occurrences
                stats['minimum_record_tokens']=length if stats['minimum_record_tokens'] is None else min(length,stats['minimum_record_tokens'])
                stats['maximum_record_tokens']=max(length,stats['maximum_record_tokens'])
                stats['records_over_current_tokenizer_limit']+=int(length>4096)
                for token,count in counts.items():
                    stats['token_counts'][token]+=count;stats['occurrence_weighted_token_counts'][token]+=count*occurrences
                record['processed_records']+=1;record['last_group']=group
                processed+=1;characters+=len(text)
            if source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_group'],)).fetchone() is None:
                if record['processed_records']!=record['total_records']:raise ValueError('Byte-statistics record count mismatch.')
                if indexes.read(root,record['index_id'])['revision']!=record['index_revision']:raise ValueError('Source index revision changed.')
                record['status']='complete'
        return _save(root,record)
