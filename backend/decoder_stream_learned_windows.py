"""Resumable source-bound learned-tokenizer next-token windows; no model training or approval."""
import json
import platform
import unicodedata
from pathlib import Path
import sqlite3
import threading
import uuid

if __package__:
    from . import decoder_stream_fitted_tokenizer_evaluations as comparisons, decoder_stream_overlap as overlap, decoder_stream_indexes as indexes
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_fitted_tokenizer_evaluations as comparisons
    import decoder_stream_overlap as overlap
    import decoder_stream_indexes as indexes
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_CHARACTERS=1024*1024


def _folder(root,audit_id):
    # Reuse the established UUID validator without sharing the index namespace.
    indexes._folder(root,audit_id)
    return Path(root)/'decoder-stream-learned-windows'/audit_id


def _runtime():
    return {'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version}


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_learned_windows.py','decoder_stream_fitted_tokenizer_evaluations.py','decoder_stream_bpe.py','decoder_stream_iterative_bpe.py','decoder_bpe.py','decoder_stream_overlap.py','decoder_stream_indexes.py','run_manifest.py')},'runtime':_runtime()})


def _state(connection):
    row=connection.execute('SELECT value FROM state WHERE id=1').fetchone()
    record=json.loads(row[0]) if row else {}
    if (record.get('format')!='almg-stream-learned-windows-v1' or type(record.get('schema_version')) is not int
            or record['schema_version']!=1 or record.get('status') not in ('preparing','awaiting_publication')):
        raise ValueError('Unsupported token-window preparation state.')
    return record


def _sources(root,comparison_id,overlap_id,full=True):
    comparison=comparisons.read(root,comparison_id)
    if comparison['fit_kind'] not in ('one_merge','iterative'):
        raise ValueError('Learned streamed windows currently require a reviewed whole-split byte-BPE codec; character-BPE admission remains unavailable.')
    if comparison['status']!='complete' or comparison.get('all_records_lossless') is not True:
        raise ValueError('Complete a lossless full-index comparison before preparing learned-tokenizer windows.')
    fitted,index,codec,signatures=comparisons._binding(root,comparison['fit_id'],comparison['fit_kind'],full)
    if (comparison['fit_revision']!=fitted['revision'] or comparison['tokenizer_sha256']!=fitted['tokenizer_sha256']
            or comparison['index_id']!=index['id'] or comparison['index_revision']!=index['revision']
            or comparison['processed_records']!=index['unique_records']
            or any(value['records']!=index['split_counts'][split] or value['lossless_records']!=value['records']
                   or not value['round_trip_verified'] for split,value in comparison['splits'].items())):
        raise ValueError('Comparison, fitted tokenizer and source population do not match.')
    overlap_folder=overlap._folder(root,overlap_id)
    report=overlap.read(root,overlap_id) if full else json.loads((overlap_folder/'manifest.json').read_text(encoding='utf-8'))
    if (report.get('status')!='complete' or report.get('revision')!=digest({k:v for k,v in report.items() if k!='revision'})
            or report['index_id']!=index['id'] or report['index_revision']!=index['revision']):
        raise ValueError('Complete a matching overlap report before preparing learned windows.')
    if report['cross_split_pairs']:
        raise ValueError('Cross-split near-duplicate findings block learned-tokenizer windows. Review affected sources first.')
    if (report['method'].get('name')!='word_shingle_jaccard' or report['method'].get('shingle_words')!=5
            or report['method'].get('minimum_words')!=12 or report['method'].get('threshold')!=.8
            or report['processed_pairs']!=report['total_pairs'] or report['total_pairs']!=index['unique_records']*(index['unique_records']-1)//2):
        raise ValueError('Overlap method or exhaustive coverage does not match the learned-window policy.')
    if not all(index['split_counts'].values()):raise ValueError('All saved splits need nonempty populations.')
    paths={'comparison':comparisons._folder(root,comparison_id)/'report.json',
           'overlap_manifest':overlap_folder/'manifest.json','overlap_database':overlap_folder/'overlap.sqlite3'}
    signatures.update({key:comparisons._signature(path) for key,path in paths.items()})
    return {'index':index,'fit':fitted,'comparison':comparison,'overlap':report,'file_signatures':signatures},codec


def review(root,comparison_id,overlap_id):return _sources(root,comparison_id,overlap_id)[0]


def begin(root,comparison_id,overlap_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm learned-tokenizer window preparation; token IDs can reconstruct source text.')
    current=review(root,comparison_id,overlap_id)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('The learned-window review changed. Reopen it before preparing.')
    index=current['index'];fitted=current['fit'];report=current['overlap']
    record={'format':'almg-stream-learned-windows-v1','schema_version':1,'id':uuid.uuid4().hex,'status':'preparing',
            'comparison_id':comparison_id,'overlap_id':overlap_id,'reviewed_sources':current,
            'index_id':index['id'],'index_revision':index['revision'],'vocabulary_size':fitted['vocabulary_size'],
            'fit_id':fitted['id'],'fit_kind':current['comparison']['fit_kind'],'tokenizer_sha256':fitted['tokenizer_sha256'],
            'source_id':index['source_id'],'source_name':index['source_name'],'source_sha256':index['source_sha256'],
            'total_records':index['unique_records'],'processed_records':0,'last_group':'','source_occurrences':0,
            'window_counts':{part:0 for part in ('train','validation','test')},'encoded_tokens':0,'target_tokens':0,
            'encoded_token_counts':{part:0 for part in ('train','validation','test')},
            'implementation_sha256':_implementation(),'runtime':_runtime(),'training_approved':False,
            'method':{'version':1,'window_tokens':17,'stride':16,'respect_document_boundaries':True,
                      'population':'all_unique_normalized_records','source_occurrences_expanded':False,
                      'gate':'lossless_full_index_comparison_and_exhaustive_cross_split_zero',
                      'short_pairs_skipped':report['short_pairs_skipped'],
                      'limitations':'Lexical gate only; short/semantic overlap can remain unchecked. Learned IDs encode original text. No model training approval.'},
            'policy':'learned_token_windows_only_training_disabled'}
    directory=_folder(root,record['id']);directory.mkdir(parents=True)
    with indexes._connect(directory/'windows.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        db.execute('CREATE TABLE documents(group_sha256 TEXT PRIMARY KEY,split TEXT NOT NULL,first_line INTEGER NOT NULL,first_byte_offset INTEGER NOT NULL,raw_line_sha256 TEXT NOT NULL,occurrences INTEGER NOT NULL,token_count INTEGER NOT NULL)')
        db.execute('CREATE TABLE windows(group_sha256 TEXT NOT NULL,token_offset INTEGER NOT NULL,split TEXT NOT NULL,tokens TEXT NOT NULL,PRIMARY KEY(group_sha256,token_offset))')
        db.execute('CREATE INDEX windows_split ON windows(split,group_sha256,token_offset)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(record),))
    return record


def _publish(root,record):
    folder=_folder(root,record['id'])
    manifest={**record,'status':'complete','files':{'windows.sqlite3':file_digest(folder/'windows.sqlite3')}}
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
        with indexes._connect(folder/'windows.sqlite3',True) as db:record=_state(db)
        if record['id']!=audit_id:raise ValueError('Token-window preparation ID mismatch.')
        path=folder/'manifest.json'
        if path.exists():
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if (manifest.get('status')!='complete'
                    or {key:value for key,value in manifest.items() if key in record and key!='status'}!={key:value for key,value in record.items() if key!='status'}
                    or manifest.get('files')!={'windows.sqlite3':file_digest(folder/'windows.sqlite3')}
                    or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})):
                raise ValueError('Token-window preparation integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:
        raise ValueError('Token-window preparation is unavailable or incomplete.') from error


def list_audits(root,index_id):
    indexes.read(root,index_id)
    directory=Path(root)/'decoder-stream-learned-windows';result=[]
    for folder in sorted(directory.iterdir()) if directory.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def step(root,audit_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing learned-tokenizer window preparation.')
    with _LOCK:
        record=read(root,audit_id)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Learned-window implementation changed; preserve progress and start a newly reviewed preparation.')
        current,tokenizer=_sources(root,record['comparison_id'],record['overlap_id'],False)
        if current!=record['reviewed_sources']:raise ValueError('Learned-window source bindings changed; committed progress is preserved.')
        if record['status']=='awaiting_publication':
            if review(root,record['comparison_id'],record['overlap_id'])!=current:raise ValueError('Publication source review changed.')
            return _publish(root,record)
        database=indexes._folder(root,record['index_id'])/'records.sqlite3'
        with indexes._connect(_folder(root,audit_id)/'windows.sqlite3') as db,indexes._connect(database,True) as source:
            db.execute('BEGIN IMMEDIATE');record=_state(db)
            cursor=source.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_group'],))
            processed=characters=0
            while processed<MAX_BATCH_RECORDS and characters<MAX_BATCH_CHARACTERS:
                row=cursor.fetchone()
                if row is None:break
                group,text,split,line,offset,raw_sha,occurrences=row
                if digest(text)!=group:raise ValueError('Source text no longer matches its saved group.')
                tokens=tokenizer.encode(text)
                if (len(tokens)<2 or any(type(value) is not int or not 0<=value<record['vocabulary_size'] for value in tokens)):
                    raise ValueError(f'Record {group} at source line {line} needs at least two valid learned tokens for next-token targets.')
                db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',(group,split,line,offset,raw_sha,occurrences,len(tokens)))
                for start in range(0,len(tokens)-1,16):
                    window=tokens[start:start+17]
                    db.execute('INSERT INTO windows VALUES(?,?,?,?)',(group,start,split,json.dumps(window)))
                    record['window_counts'][split]+=1;record['target_tokens']+=len(window)-1
                record['processed_records']+=1;record['last_group']=group;record['source_occurrences']+=occurrences
                record['encoded_tokens']+=len(tokens);record['encoded_token_counts'][split]+=len(tokens)
                processed+=1;characters+=len(text)
            complete=source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_group'],)).fetchone() is None
            final,_=_sources(root,record['comparison_id'],record['overlap_id'],complete)
            if final!=current:raise ValueError('Learned-window sources changed during processing; committed progress is preserved.')
            if complete:
                expected={part:value['encoded_tokens'] for part,value in current['comparison']['splits'].items()}
                if (record['processed_records']!=record['total_records'] or not all(record['window_counts'].values())
                        or record['encoded_token_counts']!=expected or record['target_tokens']!=record['encoded_tokens']-record['total_records']):
                    raise ValueError('Learned-window populations or token totals do not match the completed comparison.')
                record['status']='awaiting_publication'
            db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),))
        return _publish(root,record) if record['status']=='awaiting_publication' else record


def record_page(root,report_id,confirmed,cursor=None,split='all',limit=10):
    import re
    if confirmed is not True:raise ValueError('Confirm local token-window review; token IDs encode source text.')
    if type(limit) is not int or not 1<=limit<=20 or split not in ('all','train','validation','test'):
        raise ValueError('Choose a saved split and page size from 1 to 20.')
    report=read(root,report_id)
    if report['status']!='complete':raise ValueError('Complete token-window preparation before reviewing windows.')
    group='';offset=-1
    if cursor is not None:
        if (not isinstance(cursor,dict) or set(cursor)!={'revision','after_group','after_offset','split'}
                or cursor.get('revision')!=report['revision'] or cursor.get('split')!=split
                or not isinstance(cursor.get('after_group'),str) or not re.fullmatch('[a-f0-9]{64}',cursor['after_group'])
                or type(cursor.get('after_offset')) is not int or not 0<=cursor['after_offset']<=65536):
            raise ValueError('The token-window cursor changed. Reopen the first page.')
        group=cursor['after_group'];offset=cursor['after_offset']
    sql=('SELECT w.group_sha256,w.token_offset,w.split,w.tokens,d.first_line,d.first_byte_offset,d.raw_line_sha256,d.occurrences '
         'FROM windows w JOIN documents d ON d.group_sha256=w.group_sha256 '
         'WHERE (w.group_sha256>? OR (w.group_sha256=? AND w.token_offset>?))')
    parameters=[group,group,offset]
    if split!='all':sql+=' AND w.split=?';parameters.append(split)
    sql+=' ORDER BY w.group_sha256,w.token_offset LIMIT ?';parameters.append(limit+1)
    with indexes._connect(_folder(root,report_id)/'windows.sqlite3',True) as db:rows=db.execute(sql,parameters).fetchall()
    records=[]
    for group,offset,part,tokens,line,source_offset,raw_sha,occurrences in rows[:limit]:
        ids=json.loads(tokens)
        records.append({'group':group,'token_offset':offset,'split':part,'token_ids':ids,
                        'first_line':line,'first_byte_offset':source_offset,'raw_line_sha256':raw_sha,
                        'occurrences':occurrences,'source_sha256':report['source_sha256'],
                        'text_excerpt':'Token IDs: '+json.dumps(ids),'excerpt_truncated':False})
    return {'format':'almg-stream-learned-window-page-v1','schema_version':1,'records':records,'split':split,'read_only':True,
            'next_cursor':{'revision':report['revision'],'after_group':records[-1]['group'],
                           'after_offset':records[-1]['token_offset'],'split':split} if len(rows)>limit else None}


def read_batch(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):
    if confirmed is not True:raise ValueError('Confirm learned model-input inspection; IDs encode source text.')
    if type(batch_size) is not int or not 1<=batch_size<=16 or split not in ('train','validation','test'):
        raise ValueError('Choose a saved split and 1 to 16 learned windows.')
    record=read(root,window_id)
    if record['status']!='complete' or not isinstance(reviewed,dict) or reviewed!=record:
        raise ValueError('Review the exact completed learned-window version before inspecting batches.')
    if review(root,record['comparison_id'],record['overlap_id'])!=record['reviewed_sources']:
        raise ValueError('Learned-window source evidence changed.')
    page=record_page(root,window_id,True,cursor,split,batch_size)
    return _assemble(window_id,record,split,page)


def _assemble(window_id,record,split,page):
    inputs=[];targets=[];masks=[];lengths=[];provenance=[]
    for row in page['records']:
        ids=row['token_ids']
        if (not 2<=len(ids)<=17 or row['split']!=split
                or any(type(value) is not int or not 0<=value<record['vocabulary_size'] for value in ids)):
            raise ValueError('Learned IDs or splits do not match the saved model-input contract.')
        length=len(ids)-1;padding=16-length
        inputs.append(ids[:-1]+[0]*padding);targets.append(ids[1:]+[0]*padding)
        masks.append([1]*length+[0]*padding);lengths.append(length)
        provenance.append({key:row[key] for key in ('group','token_offset','split','first_line','first_byte_offset','raw_line_sha256','occurrences','source_sha256')})
    return {'format':'almg-stream-learned-model-batch-v1','schema_version':1,'windows_id':window_id,'windows_revision':record['revision'],
            'split':split,'rows':len(inputs),'sequence_width':16,'vocabulary_size':record['vocabulary_size'],
            'tokenizer_sha256':record['tokenizer_sha256'],'inputs':inputs,'targets':targets,'loss_mask':masks,'sequence_lengths':lengths,
            'real_target_tokens':sum(lengths),'provenance':provenance,'next_cursor':page['next_cursor'],
            'method':{'version':1,'padding_value':0,'padding_is_special_token':False,'loss_mask_required':True,
                      'document_boundaries_preserved':True,'source_occurrences_expanded':False,'model_execution_enabled':False},
            'training_approved':False}
