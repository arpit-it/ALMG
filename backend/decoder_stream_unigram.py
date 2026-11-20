"""Resumable five-update full-training fixed-candidate Unigram EM; no model training."""
import base64
import io
import json
import math
from pathlib import Path
import platform
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unicodedata
import uuid
import zipfile

if __package__:
    from . import decoder_stream_unigram_candidates as candidates,decoder_stream_indexes as indexes
    from .decoder_unigram import UnigramTokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_unigram_candidates as candidates
    import decoder_stream_indexes as indexes
    from decoder_unigram import UnigramTokenizer
    from run_manifest import digest,file_digest

MAX_BATCH_RECORDS=100
MAX_BATCH_BYTES=1024*1024
_LOCK=threading.RLock()


class StreamUnigram(UnigramTokenizer):
    def __init__(self,alphabet,pieces,probabilities,chain,cap,records,initializer_sha256,history=None):
        if type(records) is not int or records<1:raise ValueError('Bind Unigram to nonempty training records.')
        # Reuse the established SHA validator without changing piece IDs or history.
        if not isinstance(initializer_sha256,str) or len(initializer_sha256)!=64 or any(c not in '0123456789abcdef' for c in initializer_sha256):raise ValueError('Bind the frozen candidate initializer.')
        super().__init__(alphabet,pieces,probabilities,chain,cap,history)
        self.training_records=records;self.initializer_sha256=initializer_sha256

    @staticmethod
    def normalized(text):
        if not isinstance(text,str):raise ValueError('Provide Unicode text.')
        text=unicodedata.normalize('NFC',text);encoded=text.encode('utf-8')
        if not 1<=len(encoded)<=65536:raise ValueError('Full-split Unigram records must fit 1 to 65536 UTF-8 bytes.')
        return text,encoded

    def decode(self,tokens):
        if (not isinstance(tokens,list) or not 1<=len(tokens)<=65536
                or any(type(token) is not int or not 0<=token<len(self.pieces) for token in tokens)):
            raise ValueError('Provide bounded full-split Unigram IDs.')
        text=''.join(self.pieces[token] for token in tokens)
        if len(text.encode('utf-8'))>65536:raise ValueError('Decoded Unigram text exceeds the whole-record limit.')
        return text

    def artifact(self):
        return {'format':'almg-stream-unigram-v1','schema_version':1,'base':super().artifact(),
                'training_binding':{'method':'ordered_unique_training_group_chain_v1','chain_sha256':self.training_sha256,
                                    'records':self.training_records,'initializer_sha256':self.initializer_sha256},
                'maximum_record_utf8_bytes':65536,'em_updates':max(0,len(self.history)-1),'candidates_frozen':True}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','base','training_binding','maximum_record_utf8_bytes','em_updates','candidates_frozen'}:raise ValueError('Unsupported full-split Unigram artifact.')
        base=UnigramTokenizer.restore(artifact['base']);binding=artifact['training_binding']
        if len(base.history)!=6:raise ValueError('Complete five checked EM updates before restoring a full-split codec.')
        model=cls(base.alphabet,base.pieces,base.probabilities,binding['chain_sha256'],base.vocabulary_size,binding['records'],binding['initializer_sha256'],base.history)
        if type(artifact.get('schema_version')) is not int or digest(artifact)!=digest(model.artifact()):raise ValueError('Unigram fitting policy or binding changed.')
        return model


def _folder(root,identifier):
    indexes._folder(root,identifier)
    return Path(root)/'decoder-stream-unigram-fits'/identifier


def _implementation():
    return digest({'files':{name:file_digest(Path(__file__).with_name(name)) for name in
        ('decoder_stream_unigram.py','decoder_unigram.py','decoder_character_bpe.py','decoder_bpe.py','decoder_stream_unigram_candidates.py','decoder_stream_character_bpe.py','decoder_stream_indexes.py','decoder_stream_permissions.py','run_manifest.py')},
        'python':platform.python_version(),'unicode':unicodedata.unidata_version,'sqlite':sqlite3.sqlite_version})


def _binding(root,candidate_id,full):
    candidate=candidates.read(root,candidate_id)
    if candidate['status']!='complete':raise ValueError('Complete the frozen Unigram candidate inventory first.')
    index,signatures,permission=candidates.sources._binding(root,candidate['index_id'],full)
    if index['revision']!=candidate['review']['index_revision'] or permission!=candidate['review']['source_permission_review']:
        raise ValueError('Candidate source or permission review changed.')
    for name in ('manifest.json','counts.sqlite3'):
        path=candidates._folder(root,candidate_id)/name;stat=path.stat()
        signatures[name]={'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'ctime_ns':stat.st_ctime_ns,'inode':stat.st_ino}
    if {k:signatures[k] for k in ('database','original')}!=candidate['review']['source_signatures']:raise ValueError('Candidate source signatures changed.')
    return candidate,index,signatures,permission


def review(root,candidate_id):
    candidate,index,signatures,permission=_binding(root,candidate_id,True)
    value={'format':'almg-stream-unigram-fit-review-v1','schema_version':1,'candidate':candidate,'candidate_id':candidate_id,
           'index_id':index['id'],'index_revision':index['revision'],'source_signatures':signatures,'source_permission_review':permission,
           'source_provenance':candidate['review']['source_provenance'],'vocabulary_cap':candidate['review']['vocabulary_cap'],
           'implementation_sha256':_implementation(),'em_updates':5,'complete_training_passes':6,
           'scope':'all_unique_training_records_only_frozen_candidates_no_pruning_no_sampling',
           'model_training_enabled':False,'release_approved':False}
    value['revision']=digest(value);return value


def _state(db):
    record=json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
    if (record.get('format')!='almg-stream-unigram-fit-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
            or record.get('status') not in ('fitting','awaiting_publication')
            or record.get('model_training_enabled') is not False or record.get('release_approved') is not False
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):
        raise ValueError('Unigram fitting progress integrity check failed.')
    return record


def _write(db,record):
    record={k:v for k,v in record.items() if k!='revision'};record['revision']=digest(record)
    db.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record,allow_nan=False),));return record


def begin(root,candidate_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm five full-training-split Unigram EM updates; no model training.')
    if not isinstance(reviewed,dict) or reviewed!=review(root,candidate_id):raise ValueError('Unigram fitting review changed.')
    initial=reviewed['candidate']['initializer']
    record={'format':'almg-stream-unigram-fit-v1','schema_version':1,'id':uuid.uuid4().hex,'status':'fitting',
            'candidate_id':candidate_id,'review':reviewed,'index_id':reviewed['index_id'],
            'total_records':reviewed['candidate']['total_records'],'processed_records':0,'last_group':'',
            'completed_passes':0,'em_updates':0,'history':[],'probabilities':initial['initial_probabilities'],
            'expected_counts':[0.]*len(initial['pieces']),'pass_likelihood':0.,'pass_bytes':0,'pass_chain_sha256':digest([]),
            'implementation_sha256':_implementation(),'model_training_enabled':False,'release_approved':False}
    folder=_folder(root,record['id']);folder.mkdir(parents=True)
    with indexes._connect(folder/'work.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)');db.execute('INSERT INTO state VALUES(1,?)',('{}',));record=_write(db,record)
    return record


def _codec(record,published=False):
    candidate=record['review']['candidate'];initial=candidate['initializer']
    return StreamUnigram(initial['alphabet'],initial['pieces'],record['probabilities'],candidate['training_chain_sha256'],record['review']['vocabulary_cap'],
                         record['total_records'],digest(initial),record['history'] if published else None)


def read(root,identifier):
    try:
        folder=_folder(root,identifier)
        with indexes._connect(folder/'work.sqlite3',True) as db:record=_state(db)
        if record['id']!=identifier:raise ValueError('Unigram fitting ID changed.')
        if not (folder/'artifacts').exists():return record
        path=folder/'artifacts';manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'));artifact=json.loads((path/'tokenizer.json').read_text(encoding='utf-8'))
        codec=StreamUnigram.restore(artifact)
        if (record['status']!='awaiting_publication' or record['completed_passes']!=6 or record['em_updates']!=5 or manifest.get('status')!='complete'
                or manifest.get('job_revision')!=record['revision'] or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or manifest.get('files')!={'tokenizer.json':file_digest(path/'tokenizer.json')} or manifest.get('tokenizer_sha256')!=digest(artifact)
                or codec.artifact()!=_codec(record,True).artifact() or manifest.get('vocabulary_size')!=len(codec.pieces)
                or any(manifest.get(k)!=v for k,v in record.items() if k not in ('status','revision'))):raise ValueError('Published Unigram codec integrity check failed.')
        return manifest
    except (OSError,sqlite3.Error,TypeError,KeyError,AttributeError) as error:raise ValueError('Unigram fit unavailable; preserve its files and restore verified storage.') from error


def _publish(root,record):
    folder=_folder(root,record['id']);codec=_codec(record,True)
    with TemporaryDirectory(prefix='.publish-',dir=folder) as temporary:
        staged=Path(temporary)/'artifacts';staged.mkdir();artifact=codec.artifact()
        (staged/'tokenizer.json').write_text(json.dumps(artifact,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        manifest={k:v for k,v in record.items() if k!='revision'}
        manifest.update(status='complete',job_revision=record['revision'],vocabulary_size=len(codec.pieces),tokenizer_sha256=digest(artifact),files={'tokenizer.json':file_digest(staged/'tokenizer.json')})
        manifest['revision']=digest(manifest);(staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8');staged.rename(folder/'artifacts')
    return read(root,record['id'])


def step(root,identifier,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing the saved full-split Unigram fit.')
    with _LOCK:
        record=read(root,identifier)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Unigram implementation changed. Preserve progress and start a newly reviewed fit.')
        candidate,index,signatures,permission=_binding(root,record['candidate_id'],False)
        approved=record['review']
        if candidate!=approved['candidate'] or index['revision']!=approved['index_revision'] or signatures!=approved['source_signatures'] or permission!=approved['source_permission_review']:
            raise ValueError('Unigram candidate/source bindings changed; committed progress is preserved.')
        if record['status']=='awaiting_publication':
            if review(root,record['candidate_id'])!=approved:raise ValueError('Unigram publication review changed.')
            return _publish(root,record)
        codec=_codec(record);processed=bytes_read=0
        try:
            with indexes._connect(_folder(root,identifier)/'work.sqlite3') as db,indexes._connect(indexes._folder(root,record['index_id'])/'records.sqlite3',True) as source:
                db.execute('BEGIN IMMEDIATE');record=_state(db)
                rows=source.execute('SELECT group_sha256,text FROM documents WHERE split=? AND group_sha256>? ORDER BY group_sha256',('train',record['last_group']))
                while processed<MAX_BATCH_RECORDS and bytes_read<MAX_BATCH_BYTES:
                    row=rows.fetchone()
                    if row is None:break
                    group,text=row
                    if digest(text)!=group:raise ValueError('Unigram training record no longer matches its group.')
                    normalized,encoded=codec.normalized(text);likelihood,counts=codec._expected(normalized)
                    if not math.isfinite(likelihood) or len(counts)!=len(record['expected_counts']) or any(not math.isfinite(value) or value<0 for value in counts):raise ValueError('Unigram expected counts or likelihood are invalid.')
                    record['expected_counts']=[a+b for a,b in zip(record['expected_counts'],counts)];record['pass_likelihood']+=likelihood
                    record['processed_records']+=1;record['last_group']=group;record['pass_bytes']+=len(encoded)
                    record['pass_chain_sha256']=digest({'previous':record['pass_chain_sha256'],'group_sha256':group});processed+=1;bytes_read+=len(encoded)
                complete=source.execute('SELECT 1 FROM documents WHERE split=? AND group_sha256>? LIMIT 1',('train',record['last_group'])).fetchone() is None
                current,current_index,current_sig,current_permission=_binding(root,record['candidate_id'],complete)
                if current!=candidate or current_index!=index or current_sig!=signatures or current_permission!=permission:raise ValueError('Sources changed during Unigram EM; committed progress is preserved.')
                if complete:
                    if record['processed_records']!=record['total_records'] or record['pass_bytes']!=candidate['training_bytes'] or record['pass_chain_sha256']!=candidate['training_chain_sha256']:
                        raise ValueError('Unigram pass population changed from the frozen candidates.')
                    value=record['pass_likelihood']
                    if record['history'] and value<record['history'][-1]-1e-6:raise ValueError('Unigram EM likelihood decreased; no tokenizer published.')
                    record['history'].append(value);record['completed_passes']+=1
                    if record['completed_passes']==6:record['status']='awaiting_publication'
                    else:
                        counts=[value+1e-12 for value in record['expected_counts']];mass=math.fsum(counts)
                        if not math.isfinite(mass) or mass<=0:raise ValueError('Unigram EM probability mass is invalid.')
                        record.update(probabilities=[value/mass for value in counts],em_updates=record['em_updates']+1,processed_records=0,last_group='',
                                      expected_counts=[0.]*len(counts),pass_likelihood=0.,pass_bytes=0,pass_chain_sha256=digest([]))
                record=_write(db,record)
            return _publish(root,record) if record['status']=='awaiting_publication' else record
        except (OSError,sqlite3.Error) as error:raise ValueError('Unigram storage unavailable; committed progress is preserved. Restore storage and explicitly resume.') from error


def list_fits(root,candidate_id):
    candidates.read(root,candidate_id);parent=Path(root)/'decoder-stream-unigram-fits';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['candidate_id']==candidate_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def export(root,identifier,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm private full-split Unigram export.')
    record=read(root,identifier)
    if record['status']!='complete' or reviewed!=record:raise ValueError('Review the exact completed Unigram codec before export.')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json','tokenizer.json'):archive.writestr(name,(_folder(root,identifier)/'artifacts'/name).read_bytes())
    if read(root,identifier)!=record:raise ValueError('Unigram codec changed during export.')
    payload=buffer.getvalue();return {'name':f'whole-split-unigram-{identifier[:8]}.zip','bytes':len(payload),'data':base64.b64encode(payload).decode()}
