"""Atomic fixed-byte tokenizer artifacts bound to streamed training records only."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unicodedata
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_stream_token_stats as statistics
    from .decoder_tokenizer import ByteTokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_stream_token_stats as statistics
    from decoder_tokenizer import ByteTokenizer
    from run_manifest import digest,file_digest


def _folder(root,tokenizer_id):
    indexes._folder(root,tokenizer_id)
    return Path(root)/'decoder-stream-tokenizers'/tokenizer_id


def read(root,tokenizer_id):
    folder=_folder(root,tokenizer_id)
    try:
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('format')!='almg-stream-byte-tokenizer-v1' or type(manifest.get('schema_version')) is not int
                or manifest['schema_version']!=1 or manifest.get('id')!=tokenizer_id
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or manifest.get('files')!={'tokenizer.json':file_digest(folder/'tokenizer.json')}):
            raise ValueError('Streamed tokenizer integrity check failed.')
        artifact=json.loads((folder/'tokenizer.json').read_text(encoding='utf-8'))
        tokenizer=ByteTokenizer.restore(artifact)
        if (tokenizer.fingerprint()!=manifest['tokenizer_sha256']
                or artifact['training_documents_sha256']!=manifest['training_documents_sha256']):
            raise ValueError('Streamed tokenizer training binding changed.')
        return manifest
    except (OSError,TypeError,KeyError) as error:raise ValueError('Saved streamed tokenizer is unavailable.') from error


def list_tokenizers(root,index_id):
    indexes.read(root,index_id)
    parent=Path(root)/'decoder-stream-tokenizers';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            manifest=read(root,folder.name)
            if manifest['index_id']==index_id:result.append(manifest)
        except ValueError:continue
    return result[-20:]


def prepare(root,report_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm the fixed-byte tokenizer and training-only source binding.')
    report=statistics.read(root,report_id)
    if report['status']!='complete':raise ValueError('Complete byte distribution analysis before saving a tokenizer.')
    if not isinstance(reviewed,dict) or reviewed!=report:raise ValueError('The byte distribution review changed. Reopen it before saving.')
    if any(part['records_over_current_tokenizer_limit'] for part in report['splits'].values()):
        raise ValueError('Resolve records over the current 4096-byte tokenizer limit before saving.')
    index=indexes.read(root,report['index_id'])
    if index['status']!='complete' or index['revision']!=report['index_revision']:raise ValueError('The source index no longer matches the byte distribution report.')
    database=indexes._folder(root,index['id'])/'records.sqlite3';signature=indexes._signature(database)
    binding=hashlib.sha256();binding.update(b'[');counts={part:0 for part in ('train','validation','test')}
    validator=ByteTokenizer('0'*64)
    with indexes._connect(database,True) as source:
        for text,split in source.execute('SELECT text,split FROM documents ORDER BY group_sha256'):
            validator.encode(text)  # Validate each record, including held-out documents, without retaining its tokens.
            if split=='train':
                if counts['train']:binding.update(b',')
                binding.update(json.dumps(unicodedata.normalize('NFC',text),ensure_ascii=False,separators=(',',':')).encode('utf-8'))
            counts[split]+=1
    binding.update(b']')
    if not counts['train'] or counts!={part:value['unique_records'] for part,value in report['splits'].items()}:
        raise ValueError('Training population or split counts do not match the reviewed index.')
    if indexes._signature(database)!=signature or indexes.read(root,index['id'])['revision']!=index['revision']:
        raise ValueError('The source index changed during tokenizer preparation.')
    tokenizer=ByteTokenizer(binding.hexdigest());artifact=tokenizer.artifact();tokenizer_id=uuid.uuid4().hex
    manifest={'format':'almg-stream-byte-tokenizer-v1','schema_version':1,'id':tokenizer_id,
              'index_id':index['id'],'index_revision':index['revision'],'report_id':report_id,'report_revision':report['revision'],
              'source_provenance':{key:index[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
              'split_counts':counts,'training_documents_sha256':binding.hexdigest(),'tokenizer_sha256':tokenizer.fingerprint(),
              'method':{'version':1,'format':artifact['format'],'vocabulary_size':256,'vocabulary_fitted':False,
                        'training_binding':'sha256_of_canonical_NFC_training_text_array_ordered_by_group',
                        'validation_and_test_in_training_binding':False,'maximum_document_bytes':4096,
                        'limitations':'Fixed byte alphabet only; no BPE training, special tokens or streamed training admission.'},
              'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_stream_tokenizers.py','decoder_tokenizer.py')}),
              'training_approved':False}
    parent=Path(root)/'decoder-stream-tokenizers';parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.tokenizer-',dir=parent) as temporary:
        staged=Path(temporary)/'tokenizer';staged.mkdir()
        (staged/'tokenizer.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
        manifest['files']={'tokenizer.json':file_digest(staged/'tokenizer.json')};manifest['revision']=digest(manifest)
        (staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        staged.rename(parent/tokenizer_id)
    return read(root,tokenizer_id)
