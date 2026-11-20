"""Approved bounded training-only samples from immutable streamed text indexes."""
import base64
from datetime import datetime, timezone
import io
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
import zipfile

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_streams as streams, decoder_stream_permissions as permissions
    from . import decoder_tokenizer_experiments as experiments
    from .decoder_special_tokens import SpecialTokenizer, restore_base
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_streams as streams
    import decoder_stream_permissions as permissions
    import decoder_tokenizer_experiments as experiments
    from decoder_special_tokens import SpecialTokenizer, restore_base
    from run_manifest import digest, file_digest

LIMITS = {'train':16, 'validation':8, 'test':8}


def _folder(root, identifier):
    indexes._folder(root, identifier)
    return Path(root)/'decoder-stream-tokenizer-experiments'/identifier


def _collect_sample(root, index_id, config):
    experiments._config(config)
    index = indexes.read(root, index_id)
    if index['status'] != 'complete':raise ValueError('Complete the streamed text index before reviewing a tokenizer sample.')
    original = streams.folder(root, index['source_id'])/'source.bin'
    signature = indexes._signature(original)
    if signature['bytes'] != index['source_bytes'] or file_digest(original) != index['source_sha256']:
        raise ValueError('Stored source changed. Preserve the index and verify original source bytes.')
    database = indexes._folder(root,index_id)/'records.sqlite3'
    database_signature = indexes._signature(database)
    permission = permissions.snapshot(root, index)
    rows = []
    with indexes._connect(database, True) as connection:
        for split, limit in LIMITS.items():
            selected = connection.execute('SELECT text,group_sha256,first_line,first_byte_offset,raw_line_sha256,occurrences '
                'FROM documents WHERE split=? AND length(CAST(text AS BLOB)) BETWEEN 1 AND 4096 '
                'ORDER BY group_sha256 LIMIT ?', (split,limit))
            for text,group,line,offset,raw_hash,occurrences in selected:
                if digest(text) != group:raise ValueError('Sample record content does not match its normalized group.')
                rows.append({'text':text, 'split':split, 'group_sha256':group, 'first_line':line,
                             'first_byte_offset':offset, 'raw_line_sha256':raw_hash, 'occurrences':occurrences,
                             'utf8_bytes':len(text.encode('utf-8'))})
    counts = {split:sum(row['split']==split for row in rows) for split in LIMITS}
    if not all(counts.values()):raise ValueError('Each split needs at least one whole record within the 4096-byte sample limit.')
    if (indexes.read(root,index_id) != index or indexes._signature(database) != database_signature or indexes._signature(original) != signature
            or permissions.snapshot(root,index) != permission):
        raise ValueError('Source index or permission review changed during sampling.')
    result = {'format':'almg-stream-tokenizer-sample-review-v1', 'schema_version':1,
              'index_id':index_id, 'index_revision':index['revision'], 'config':config,
              'source_provenance':{key:index[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
              'source_permission_review':permission, 'population_split_counts':index['split_counts'], 'sample_split_counts':counts,
              'sample_records':[{key:value for key,value in row.items() if key!='text'} for row in rows],
              'training_documents_sha256':digest([row['text'] for row in rows if row['split']=='train']),
              'method':{'version':1,'order':'normalized_group_sha256_ascending_within_each_saved_split',
                        'maximum_records_per_split':dict(LIMITS),'maximum_record_utf8_bytes':4096,
                        'maximum_sample_utf8_bytes':131072,'records_are_truncated':False,
                        'oversized_records':'excluded_from_sample_not_modified_in_source',
                        'occurrence_weights':'unique_records_once', 'fitting_split':'train_only',
                        'comparisons':'sample_only_not_full_population_or_contamination_clearance'},
              'model_training_enabled':False, 'release_approved':False,
              'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in
                 ('decoder_stream_tokenizer_experiments.py','decoder_tokenizer_experiments.py','decoder_stream_indexes.py',
                  'decoder_bpe.py','decoder_character_bpe.py','decoder_unigram.py','decoder_special_tokens.py')})}
    result['revision'] = digest(result)
    return result, rows


def _sample(root, index_id, config):
    try:
        return _collect_sample(root,index_id,config)
    except (OSError,sqlite3.Error) as error:
        raise ValueError('Streamed tokenizer source is unavailable. Preserve the index and restore its verified source files.') from error


def review(root, index_id, config):return _sample(root,index_id,config)[0]


def train(root, index_id, confirmed, reviewed):
    if confirmed is not True:raise ValueError('Confirm the exact streamed tokenizer training sample; full-corpus and model training stay disabled.')
    if not isinstance(reviewed,dict):raise ValueError('Review the streamed tokenizer sample first.')
    current, rows = _sample(root,index_id,reviewed.get('config'))
    if current != reviewed:raise ValueError('The streamed tokenizer sample review changed. Reopen it before fitting.')
    algorithm,cap,labels,policy = experiments._config(current['config'])
    cls = {'byte_level_bpe':experiments.ByteBPE,'character_bpe':experiments.CharacterBPE,'unigram':experiments.UnigramTokenizer}[algorithm]
    model = cls.fit([row['text'] for row in rows if row['split']=='train'],cap-len(labels))
    if labels:model = SpecialTokenizer(model,labels,policy)
    comparison = experiments.compare(rows,model,algorithm)
    if review(root,index_id,current['config']) != current:
        raise ValueError('Streamed source or approval scope changed during fitting; no artifact published.')
    identifier = uuid.uuid4().hex
    manifest = {'format':'almg-stream-tokenizer-experiment-v1','schema_version':1,'id':identifier,
                'index_id':index_id,'sample_review':current,'algorithm':algorithm,'config':current['config'],
                'vocabulary_size':len(model.pieces),'training_documents_sha256':model.training_sha256,
                'comparison':comparison,'comparison_scope':'reviewed_sample_only',
                'approval':{'version':1,'scope':'streamed_training_sample_tokenizer_fitting_only',
                            'confirmed_at':datetime.now(timezone.utc).isoformat(),'review_revision':current['revision']},
                'tokenizer_sha256':digest(model.artifact()),'model_training_enabled':False,'release_approved':False,
                'limitations':'Deterministic bounded whole-record sample, not a representative or complete corpus fit. Oversized records are excluded. No full-population evaluation, contamination clearance or model training approval.'}
    parent = Path(root)/'decoder-stream-tokenizer-experiments';parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.sample-fit-',dir=parent) as temporary:
        staged = Path(temporary)/'experiment';staged.mkdir()
        (staged/'tokenizer.json').write_text(json.dumps(model.artifact(),ensure_ascii=False,indent=2),encoding='utf-8')
        manifest['files'] = {'tokenizer.json':file_digest(staged/'tokenizer.json')}
        manifest['revision'] = digest(manifest)
        (staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        staged.rename(parent/identifier)
    return read(root,identifier)


def read(root, identifier):
    folder = _folder(root,identifier)
    try:
        if any((folder/name).stat().st_size>256000 for name in ('manifest.json','tokenizer.json')):
            raise ValueError('Streamed tokenizer experiment exceeds its file bound.')
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        artifact = json.loads((folder/'tokenizer.json').read_text(encoding='utf-8'))
        model = SpecialTokenizer.restore(artifact) if artifact.get('format')=='almg-special-tokenizer-v1' else restore_base(artifact)
        base = model.base if isinstance(model,SpecialTokenizer) else model
        algorithm,cap,labels,policy = experiments._config(manifest['config'])
        actual_algorithm = {'almg-byte-bpe-tokenizer-v1':'byte_level_bpe','almg-character-bpe-tokenizer-v1':'character_bpe','almg-unigram-tokenizer-v1':'unigram'}[base.artifact()['format']]
        reviewed = manifest['sample_review']
        if (manifest.get('format')!='almg-stream-tokenizer-experiment-v1' or type(manifest.get('schema_version')) is not int
                or manifest['schema_version']!=1 or manifest.get('id')!=identifier
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or manifest.get('files')!={'tokenizer.json':file_digest(folder/'tokenizer.json')}
                or manifest.get('tokenizer_sha256')!=digest(artifact) or manifest.get('vocabulary_size')!=len(model.pieces)
                or manifest.get('training_documents_sha256')!=model.training_sha256
                or manifest.get('algorithm')!=algorithm or algorithm!=actual_algorithm or cap!=model.vocabulary_size
                or labels!=getattr(model,'definitions',{}) or policy!=getattr(model,'unknown_policy','reject')
                or reviewed.get('format')!='almg-stream-tokenizer-sample-review-v1'
                or reviewed.get('revision')!=digest({k:v for k,v in reviewed.items() if k!='revision'})
                or reviewed.get('index_id')!=manifest.get('index_id') or reviewed.get('config')!=manifest['config']
                or reviewed.get('training_documents_sha256')!=model.training_sha256
                or (algorithm=='unigram' and len(base.history)!=6)
                or set(manifest.get('comparison',{}))!=set(LIMITS)
                or reviewed.get('model_training_enabled') is not False or reviewed.get('release_approved') is not False
                or manifest.get('comparison_scope')!='reviewed_sample_only'
                or manifest.get('approval',{}).get('scope')!='streamed_training_sample_tokenizer_fitting_only'
                or manifest['approval'].get('review_revision')!=reviewed['revision']
                or any(value.get('used_for_fitting')!=(split=='train') for split,value in manifest['comparison'].items())
                or manifest.get('model_training_enabled') is not False or manifest.get('release_approved') is not False):
            raise ValueError('Streamed tokenizer experiment integrity check failed.')
        return manifest
    except (OSError,TypeError,KeyError,AttributeError) as error:raise ValueError('Streamed tokenizer experiment is unavailable.') from error


def list_experiments(root,index_id):
    indexes.read(root,index_id)
    parent = Path(root)/'decoder-stream-tokenizer-experiments';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            manifest=read(root,folder.name)
            if manifest['index_id']==index_id:result.append(manifest)
        except ValueError:continue
    return result[-20:]


def export(root,identifier,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm private sampled-tokenizer export; learned pieces can encode training phrases.')
    manifest=read(root,identifier)
    if not isinstance(reviewed,dict) or reviewed!=manifest:raise ValueError('The streamed tokenizer export review changed.')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json','tokenizer.json'):archive.writestr(name,(_folder(root,identifier)/name).read_bytes())
    if read(root,identifier)!=manifest:raise ValueError('Streamed tokenizer changed during export.')
    payload=buffer.getvalue()
    return {'name':f'stream-tokenizer-sample-{identifier[:8]}.zip','bytes':len(payload),'data':base64.b64encode(payload).decode()}
