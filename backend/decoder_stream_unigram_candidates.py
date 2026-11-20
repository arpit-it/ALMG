"""Resumable training-only Unigram candidate initialization; no EM or trained codec."""
from collections import Counter
import json
import math
from pathlib import Path
import platform
import shutil
import sqlite3
import threading
import unicodedata
import uuid

if __package__:
    from . import decoder_stream_character_bpe as sources,decoder_stream_indexes as indexes
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_character_bpe as sources
    import decoder_stream_indexes as indexes
    from run_manifest import digest,file_digest

MAX_BATCH_RECORDS=100
MAX_BATCH_BYTES=1024*1024
MAX_COUNTER_ENTRIES=4096
_LOCK=threading.RLock()


def _folder(root,identifier):
    indexes._folder(root,identifier)
    return Path(root)/'decoder-stream-unigram-candidates'/identifier


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
        ('decoder_stream_unigram_candidates.py','decoder_stream_character_bpe.py','decoder_stream_indexes.py','decoder_stream_permissions.py','decoder_unigram.py','run_manifest.py')},
        'python':platform.python_version(),'unicode':unicodedata.unidata_version,'sqlite':sqlite3.sqlite_version})


def review(root,index_id,cap=128):
    if type(cap) is not int or not 32<=cap<=512:raise ValueError('Choose a Unigram candidate cap from 32 to 512.')
    index,signatures,permission=sources._binding(root,index_id,True)
    if not index['split_counts']['train']:raise ValueError('A nonempty training split is required.')
    result={'format':'almg-stream-unigram-candidate-review-v1','schema_version':1,'index_id':index_id,'index_revision':index['revision'],
            'source_provenance':{key:index[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
            'source_signatures':signatures,'source_permission_review':permission,'vocabulary_cap':cap,
            'training_records':index['split_counts']['train'],'implementation_sha256':_implementation(),
            'method':{'version':1,'population':'all_unique_training_records_only','source_occurrences_expanded':False,
                      'maximum_record_utf8_bytes':65536,'maximum_piece_characters':8,'minimum_substring_frequency':2,
                      'candidate_selection':'frequency_times_length_minus_one_then_lexical','cross_word_pieces':False,
                      'cross_document_pieces':False,'em_updates':0,'tokenizer_trained':False},
            'model_training_enabled':False,'release_approved':False}
    result['revision']=digest(result);return result


def _state(db):
    value=json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
    if (value.get('format')!='almg-stream-unigram-candidate-inventory-v1' or type(value.get('schema_version')) is not int
            or value['schema_version']!=1 or value.get('status') not in ('collecting','awaiting_publication')
            or any(value.get(key) is not False for key in ('tokenizer_trained','model_training_enabled','release_approved'))
            or value.get('revision')!=digest({k:v for k,v in value.items() if k!='revision'})):
        raise ValueError('Unigram candidate progress integrity check failed.')
    return value


def _write(db,record):
    record={k:v for k,v in record.items() if k!='revision'};record['revision']=digest(record)
    db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),));return record


def begin(root,index_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm full-split Unigram candidate preparation; pieces may encode private text.')
    if not isinstance(reviewed,dict) or reviewed!=review(root,index_id,reviewed.get('vocabulary_cap')):raise ValueError('Candidate review changed. Reopen its exact source and budget.')
    if shutil.disk_usage(root).free<64*1024*1024:raise ValueError('Candidate counters need at least 64 MiB of free scratch space.')
    record={'format':'almg-stream-unigram-candidate-inventory-v1','schema_version':1,'id':uuid.uuid4().hex,'status':'collecting',
            'index_id':index_id,'review':reviewed,'total_records':reviewed['training_records'],'processed_records':0,'last_group':'',
            'training_bytes':0,'training_chain_sha256':digest([]),'implementation_sha256':_implementation(),
            'tokenizer_trained':False,'model_training_enabled':False,'release_approved':False}
    folder=_folder(root,record['id']);folder.mkdir(parents=True)
    with indexes._connect(folder/'counts.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE alphabet(character TEXT PRIMARY KEY,n INTEGER NOT NULL)')
        db.execute('CREATE TABLE substrings(piece TEXT PRIMARY KEY,n INTEGER NOT NULL)')
        db.execute('INSERT INTO state VALUES(1,?)',('{}',));record=_write(db,record)
    return record


def _initialization(db,cap):
    alphabet_rows=db.execute('SELECT character,n FROM alphabet ORDER BY character').fetchall()
    if not 1<=len(alphabet_rows)<=cap:raise ValueError('Training alphabet does not fit the reviewed cap.')
    selected=db.execute('SELECT piece,n FROM substrings WHERE n>=2 ORDER BY n*(length(piece)-1) DESC,piece LIMIT ?',
                        (cap-len(alphabet_rows),)).fetchall()
    alphabet=[char for char,n in alphabet_rows];counts=dict(alphabet_rows+selected)
    pieces=alphabet+sorted(piece for piece,n in selected);mass=sum(counts[piece] for piece in pieces)
    probabilities=[counts[piece]/mass for piece in pieces]
    if not math.isfinite(math.fsum(probabilities)) or abs(math.fsum(probabilities)-1)>1e-9:raise ValueError('Initial candidate probability mass is invalid.')
    return {'alphabet':alphabet,'pieces':pieces,'counts':[counts[piece] for piece in pieces],'initial_probabilities':probabilities,
            'candidate_vocabulary_size':len(pieces),'distinct_training_substrings':db.execute('SELECT COUNT(*) FROM substrings').fetchone()[0],
            'em_updates':0,'tokenizer_trained':False}


def _publish(root,record):
    folder=_folder(root,record['id'])
    with indexes._connect(folder/'counts.sqlite3',True) as db:initial=_initialization(db,record['review']['vocabulary_cap'])
    manifest={**record,'status':'complete','initializer':initial,'files':{'counts.sqlite3':file_digest(folder/'counts.sqlite3')}}
    manifest['revision']=digest({k:v for k,v in manifest.items() if k!='revision'})
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8');temporary.replace(folder/'manifest.json')
    finally:temporary.unlink(missing_ok=True)
    return manifest


def read(root,identifier):
    try:
        folder=_folder(root,identifier)
        with indexes._connect(folder/'counts.sqlite3',True) as db:record=_state(db)
        if record['id']!=identifier:raise ValueError('Candidate inventory ID changed.')
        if not (folder/'manifest.json').exists():return record
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        with indexes._connect(folder/'counts.sqlite3',True) as db:initial=_initialization(db,record['review']['vocabulary_cap'])
        if (record['status']!='awaiting_publication' or manifest.get('status')!='complete'
                or any(manifest.get(k)!=v for k,v in record.items() if k not in ('status','revision'))
                or manifest.get('initializer')!=initial or manifest.get('files')!={'counts.sqlite3':file_digest(folder/'counts.sqlite3')}
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})):
            raise ValueError('Unigram candidate inventory integrity check failed.')
        return manifest
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:raise ValueError('Candidate inventory unavailable; preserve its files and restore verified storage.') from error


def list_reports(root,index_id):
    indexes.read(root,index_id);parent=Path(root)/'decoder-stream-unigram-candidates';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def step(root,identifier,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing the saved Unigram candidate preparation.')
    with _LOCK:
        record=read(root,identifier)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Candidate implementation changed. Preserve progress and start a newly reviewed inventory.')
        approved=record['review'];index_id=record['index_id']
        try:
            index,sig,permission=sources._binding(root,index_id,False)
            if index['revision']!=approved['index_revision'] or sig!=approved['source_signatures'] or permission!=approved['source_permission_review']:
                raise ValueError('Source or permissions changed; committed candidate progress is preserved.')
            if record['status']=='awaiting_publication':
                if review(root,index_id,approved['vocabulary_cap'])!=approved:raise ValueError('Candidate publication review changed.')
                return _publish(root,record)
            with indexes._connect(_folder(root,identifier)/'counts.sqlite3') as db,indexes._connect(indexes._folder(root,index_id)/'records.sqlite3',True) as source:
                db.execute('BEGIN IMMEDIATE');record=_state(db)
                rows=source.execute('SELECT group_sha256,text FROM documents WHERE split=? AND group_sha256>? ORDER BY group_sha256',('train',record['last_group']))
                processed=bytes_read=0
                while processed<MAX_BATCH_RECORDS and bytes_read<MAX_BATCH_BYTES:
                    row=rows.fetchone()
                    if row is None:break
                    group,text=row
                    if digest(text)!=group:raise ValueError('Training record content no longer matches its saved group.')
                    normalized,encoded=sources.StreamCharacterBPE.normalized(text)
                    db.executemany('INSERT INTO alphabet VALUES(?,?) ON CONFLICT(character) DO UPDATE SET n=n+excluded.n',Counter(normalized).items())
                    if db.execute('SELECT COUNT(*) FROM alphabet').fetchone()[0]>approved['vocabulary_cap']:
                        raise ValueError('Training alphabet exceeds the Unigram candidate cap. Preserve progress and review a larger budget.')
                    delta=Counter()
                    def flush():
                        db.executemany('INSERT INTO substrings VALUES(?,?) ON CONFLICT(piece) DO UPDATE SET n=n+excluded.n',delta.items());delta.clear()
                    for word in normalized.split():
                        for start in range(len(word)):
                            for length in range(2,min(8,len(word)-start)+1):
                                delta[word[start:start+length]]+=1
                                if len(delta)>=MAX_COUNTER_ENTRIES:flush()
                    flush()
                    record['processed_records']+=1;record['last_group']=group;record['training_bytes']+=len(encoded)
                    record['training_chain_sha256']=digest({'previous':record['training_chain_sha256'],'group_sha256':group})
                    processed+=1;bytes_read+=len(encoded)
                complete=source.execute('SELECT 1 FROM documents WHERE split=? AND group_sha256>? LIMIT 1',('train',record['last_group'])).fetchone() is None
                current,current_sig,current_permission=sources._binding(root,index_id,complete)
                if current!=index or current_sig!=sig or current_permission!=permission:raise ValueError('Sources changed during candidate preparation; committed progress is preserved.')
                if complete:
                    if record['processed_records']!=record['total_records']:raise ValueError('Candidate training population mismatch.')
                    record['status']='awaiting_publication'
                record=_write(db,record)
            return _publish(root,record) if record['status']=='awaiting_publication' else record
        except (OSError,sqlite3.Error) as error:raise ValueError('Candidate storage unavailable; committed progress is preserved. Restore storage and explicitly resume.') from error
