"""Resumable full-index comparison of a saved sample-fitted tokenizer; no fitting."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sqlite3
import threading
import unicodedata
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_streams as streams, decoder_stream_permissions as permissions
    from . import decoder_stream_tokenizer_experiments as experiments
    from .decoder_special_tokens import SpecialTokenizer, restore_base
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_streams as streams
    import decoder_stream_permissions as permissions
    import decoder_stream_tokenizer_experiments as experiments
    from decoder_special_tokens import SpecialTokenizer, restore_base
    from run_manifest import digest, file_digest

_LOCK = threading.RLock()
MAX_BATCH_RECORDS = 100
MAX_BATCH_BYTES = 1024*1024
MAX_FINDINGS = 20


def _folder(root,identifier):
    indexes._folder(root,identifier)
    return Path(root)/'decoder-stream-tokenizer-evaluations'/identifier


def _implementation():
    return digest({'code':{name:file_digest(Path(__file__).with_name(name)) for name in
        ('decoder_stream_tokenizer_evaluations.py','decoder_stream_tokenizer_experiments.py',
         'decoder_bpe.py','decoder_character_bpe.py','decoder_unigram.py','decoder_special_tokens.py')},
        'python':platform.python_version(),'unicode':unicodedata.unidata_version})


def _signature(path):return {**indexes._signature(path),'ctime_ns':path.stat().st_ctime_ns}


def _binding(root,experiment_id,full):
    experiment = experiments.read(root,experiment_id)
    index_id = experiment['index_id'];folder=indexes._folder(root,index_id)
    if (folder/'manifest.json').stat().st_size>256000:raise ValueError('Source index manifest exceeds its supported bound.')
    index = indexes.read(root,index_id) if full else json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if (index.get('status')!='complete' or index.get('id')!=index_id
            or index.get('revision')!=digest({k:v for k,v in index.items() if k!='revision'})
            or index['revision']!=experiment['sample_review']['index_revision']):
        raise ValueError('The saved tokenizer no longer matches the complete source index.')
    database=folder/'records.sqlite3';original=streams.folder(root,index['source_id'])/'source.bin'
    signatures={'database':_signature(database),'original':_signature(original)}
    if signatures['original']['bytes']!=index['source_bytes'] or (full and file_digest(original)!=index['source_sha256']):
        raise ValueError('Original source integrity changed; saved comparison progress is preserved.')
    permission=permissions.snapshot(root,index)
    if permission!=experiment['sample_review']['source_permission_review']:
        raise ValueError('Source permissions changed from the fitted sample review. Review a new fitting sample before comparing.')
    artifact=json.loads((experiments._folder(root,experiment_id)/'tokenizer.json').read_text(encoding='utf-8'))
    model=SpecialTokenizer.restore(artifact) if artifact.get('format')=='almg-special-tokenizer-v1' else restore_base(artifact)
    if signatures!={'database':_signature(database),'original':_signature(original)}:
        raise ValueError('Source changed during comparison integrity verification.')
    return experiment,index,model,signatures


def _save(root,record):
    folder=_folder(root,record['id']);folder.mkdir(parents=True,exist_ok=True)
    record={k:v for k,v in record.items() if k!='revision'};record['revision']=digest(record)
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        temporary.replace(folder/'report.json')
    finally:temporary.unlink(missing_ok=True)
    return record


def read(root,identifier):
    try:
        path=_folder(root,identifier)/'report.json'
        if path.stat().st_size>256000:raise ValueError('Tokenizer comparison exceeds its file bound.')
        record=json.loads(path.read_text(encoding='utf-8'))
        if (record.get('format')!='almg-stream-tokenizer-evaluation-v1' or type(record.get('schema_version')) is not int
                or record['schema_version']!=1 or record.get('id')!=identifier
                or record.get('status') not in ('scanning','complete')
                or record.get('model_training_enabled') is not False or record.get('release_approved') is not False
                or record.get('tokenizer_refitted') is not False
                or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):
            raise ValueError('Full-index tokenizer comparison integrity check failed.')
        return record
    except (OSError,TypeError,KeyError) as error:raise ValueError('Saved full-index tokenizer comparison is unavailable.') from error


def begin(root,experiment_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm full-index comparison of the reviewed saved tokenizer; no refitting or model training.')
    try:
        experiment,index,_,signatures=_binding(root,experiment_id,True)
    except (OSError,sqlite3.Error) as error:raise ValueError('Restore the verified source/index files before tokenizer comparison.') from error
    if not isinstance(reviewed,dict) or reviewed!=experiment:raise ValueError('The tokenizer review changed. Reopen it before comparing.')
    return _save(root,{'format':'almg-stream-tokenizer-evaluation-v1','schema_version':1,'id':uuid.uuid4().hex,
        'status':'scanning','experiment_id':experiment_id,'experiment_revision':experiment['revision'],
        'tokenizer_sha256':experiment['tokenizer_sha256'],'index_id':index['id'],'index_revision':index['revision'],
        'source_provenance':experiment['sample_review']['source_provenance'],'source_signatures':signatures,
        'source_permission_revision':experiment['sample_review']['source_permission_review']['revision'],
        'approval':{'version':1,'scope':'full_index_tokenizer_comparison_only','confirmed_at':datetime.now(timezone.utc).isoformat()},
        'implementation_sha256':_implementation(),'total_records':index['unique_records'],'processed_records':0,'last_group':'',
        'method':{'version':1,'population':'all_unique_records_in_saved_splits','duplicates':'occurrences_reported_not_expanded',
                  'maximum_encoded_record_bytes':4096,'oversized_records':'counted_as_unsupported_without_truncation',
                  'efficiency':'lossless_encoded_records_only_including_boundaries','character_coverage':'all_records_including_unsupported',
                  'finding_sample_limit_per_category':MAX_FINDINGS,'raw_text_included':False},
        'splits':{split:{'records':0,'source_occurrences':0,'characters':0,'baseline_byte_tokens':0,
                        'uncovered_characters':0,'encoded_records':0,'lossless_records':0,'lossy_records':0,
                        'unsupported_records':0,'encoding_failures':0,'encoded_tokens':0,'lossless_tokens':0,
                        'lossless_bytes':0,'lossless_characters':0,'unknown_tokens':0,'boundary_tokens':0,
                        'round_trip_verified':False,'byte_to_token_ratio':None,'tokens_per_nfc_character':None,
                        'covered_character_fraction':None} for split in ('train','validation','test')},
        'finding_samples':{'unsupported':[],'encoding_failure':[],'lossy':[]},'all_records_lossless':False,
        'tokenizer_refitted':False,'model_training_enabled':False,'release_approved':False,
        'limitations':'Full-index comparison of a sample-fitted codec, not full-corpus fitting, contamination clearance or model training approval.'})


def list_reports(root,experiment_id):
    experiments.read(root,experiment_id);parent=Path(root)/'decoder-stream-tokenizer-evaluations';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            report=read(root,folder.name)
            if report['experiment_id']==experiment_id:result.append(report)
        except ValueError:continue
    return result[-20:]


def step(root,identifier,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing the saved full-index tokenizer comparison.')
    with _LOCK:
        record=read(root,identifier)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Comparison implementation changed; preserve progress and start a newly reviewed comparison.')
        try:
            experiment,index,model,signatures=_binding(root,record['experiment_id'],False)
            if (experiment['revision']!=record['experiment_revision'] or index['revision']!=record['index_revision']
                    or signatures!=record['source_signatures']):
                raise ValueError('Tokenizer or source changed; saved comparison progress is preserved.')
            database=indexes._folder(root,index['id'])/'records.sqlite3'
            processed=bytes_read=0
            base=model.base if isinstance(model,SpecialTokenizer) else model
            alphabet=set(base.alphabet) if hasattr(base,'alphabet') else None
            with indexes._connect(database,True) as source:
                cursor=source.execute('SELECT group_sha256,text,split,occurrences,first_line,first_byte_offset,raw_line_sha256 '
                    'FROM documents WHERE group_sha256>? ORDER BY group_sha256',(record['last_group'],))
                while processed<MAX_BATCH_RECORDS and bytes_read<MAX_BATCH_BYTES:
                    row=cursor.fetchone()
                    if row is None:break
                    group,text,split,occurrences,line,offset,raw_hash=row
                    if digest(text)!=group:raise ValueError('Indexed text no longer matches its normalized group.')
                    normalized=unicodedata.normalize('NFC',text);encoded=normalized.encode('utf-8');length=len(encoded)
                    stats=record['splits'][split]
                    stats['records']+=1;stats['source_occurrences']+=occurrences
                    stats['characters']+=len(normalized);stats['baseline_byte_tokens']+=length
                    missing=sum(char not in alphabet for char in normalized) if alphabet is not None else 0
                    stats['uncovered_characters']+=missing
                    category=None
                    if length>4096:
                        stats['unsupported_records']+=1;category='unsupported'
                    else:
                        try:
                            tokens=model.encode(normalized)
                            if not tokens or any(type(token) is not int or not 0<=token<len(model.pieces) for token in tokens):
                                raise ValueError('Invalid emitted token IDs.')
                            decoded=model.decode(tokens)
                            stats['encoded_records']+=1;stats['encoded_tokens']+=len(tokens)
                            ids=getattr(model,'special_ids',{})
                            stats['unknown_tokens']+=sum(token==ids.get('unk') for token in tokens)
                            stats['boundary_tokens']+=sum(token in [ids[role] for role in ('bos','eos') if role in ids] for token in tokens)
                            if not missing and decoded==normalized:
                                stats['lossless_records']+=1;stats['lossless_tokens']+=len(tokens)
                                stats['lossless_bytes']+=length;stats['lossless_characters']+=len(normalized)
                            else:stats['lossy_records']+=1;category='lossy'
                        except (ValueError,UnicodeError):stats['encoding_failures']+=1;category='encoding_failure'
                    if category and len(record['finding_samples'][category])<MAX_FINDINGS:
                        record['finding_samples'][category].append({'group_sha256':group,'split':split,'first_line':line,
                            'first_byte_offset':offset,'raw_line_sha256':raw_hash,'utf8_bytes':length,'uncovered_characters':missing})
                    record['processed_records']+=1;record['last_group']=group;processed+=1;bytes_read+=length
                complete=source.execute('SELECT 1 FROM documents WHERE group_sha256>? LIMIT 1',(record['last_group'],)).fetchone() is None
            current_experiment,current_index,_,current=_binding(root,record['experiment_id'],complete)
            if current_experiment!=experiment or current_index!=index or current!=signatures:raise ValueError('Source changed during comparison; saved progress is preserved.')
            if complete:
                if (record['processed_records']!=record['total_records']
                        or {split:value['records'] for split,value in record['splits'].items()}!=index['split_counts']):
                    raise ValueError('Full-index tokenizer comparison population mismatch.')
                record['status']='complete'
            for stats in record['splits'].values():
                stats['round_trip_verified']=bool(complete and stats['records'] and stats['lossless_records']==stats['records'])
                stats['covered_character_fraction']=(stats['characters']-stats['uncovered_characters'])/stats['characters'] if stats['characters'] else None
                stats['byte_to_token_ratio']=stats['lossless_bytes']/stats['lossless_tokens'] if stats['lossless_tokens'] else None
                stats['tokens_per_nfc_character']=stats['lossless_tokens']/stats['lossless_characters'] if stats['lossless_characters'] else None
            record['all_records_lossless']=bool(complete and all(stats['round_trip_verified'] for stats in record['splits'].values()))
            return _save(root,record)
        except (OSError,sqlite3.Error) as error:raise ValueError('Source or comparison storage is unavailable; saved progress is preserved. Restore verified files and resume.') from error
