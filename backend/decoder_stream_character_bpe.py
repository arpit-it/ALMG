"""Disk-backed full-training character BPE with frozen alphabet and resumable passes."""
import base64
from collections import Counter
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import platform
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unicodedata
import uuid
import zipfile

if __package__:
    from . import decoder_stream_indexes as indexes,decoder_streams as streams,decoder_stream_permissions as permissions
    from .decoder_character_bpe import CharacterBPE
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_streams as streams
    import decoder_stream_permissions as permissions
    from decoder_character_bpe import CharacterBPE
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()
MAX_BATCH_RECORDS=100
MAX_BATCH_BYTES=1024*1024


class StreamCharacterBPE(CharacterBPE):
    def __init__(self,alphabet,merges,chain,cap,records):
        if type(records) is not int or records<1:raise ValueError('A nonempty training population is required.')
        super().__init__(alphabet,merges,chain,cap);self.training_records=records

    @staticmethod
    def normalized(text):
        if not isinstance(text,str):raise ValueError('Provide Unicode text.')
        text=unicodedata.normalize('NFC',text);encoded=text.encode('utf-8')
        if not 1<=len(encoded)<=65536:raise ValueError('Whole-split character BPE records must fit 1 to 65536 UTF-8 bytes.')
        return text,encoded

    def decode(self,tokens):
        if (not isinstance(tokens,list) or not 1<=len(tokens)<=65536
                or any(type(token) is not int or not 0<=token<len(self.pieces) for token in tokens)):
            raise ValueError('Provide bounded character-BPE token IDs.')
        text=''.join(self.pieces[token] for token in tokens)
        if len(text.encode('utf-8'))>65536:raise ValueError('Decoded text exceeds the whole-record limit.')
        return text

    def artifact(self):
        return {'format':'almg-stream-character-bpe-v1','schema_version':1,'base':super().artifact(),
                'training_binding':{'method':'ordered_unique_training_group_chain_v1','initial_sha256':digest([]),
                                    'chain_sha256':self.training_sha256,'records':self.training_records},
                'maximum_record_utf8_bytes':65536,'maximum_learned_merges':511,
                'alphabet_policy':'complete_unique_training_records_frozen_before_merges'}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','base','training_binding','maximum_record_utf8_bytes','maximum_learned_merges','alphabet_policy'}:
            raise ValueError('Unsupported whole-split character BPE artifact.')
        base=CharacterBPE.restore(artifact['base']);binding=artifact['training_binding']
        result=cls(base.alphabet,base.merges,binding['chain_sha256'],base.vocabulary_size,binding['records'])
        if type(artifact.get('schema_version')) is not int or digest(artifact)!=digest(result.artifact()):raise ValueError('Character-BPE binding or policy changed.')
        return result


def _folder(root,identifier):
    indexes._folder(root,identifier)
    return Path(root)/'decoder-stream-character-bpe-fits'/identifier


def _implementation():
    return digest({'code':{name:file_digest(Path(__file__).with_name(name)) for name in
        ('decoder_stream_character_bpe.py','decoder_character_bpe.py','decoder_bpe.py','decoder_stream_indexes.py','decoder_stream_permissions.py','run_manifest.py')},
        'python':platform.python_version(),'unicode':unicodedata.unidata_version,'sqlite':sqlite3.sqlite_version})


def _binding(root,index_id,full):
    folder=indexes._folder(root,index_id)
    index=indexes.read(root,index_id) if full else json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if index.get('status')!='complete' or index.get('revision')!=digest({k:v for k,v in index.items() if k!='revision'}):raise ValueError('Complete and verify the saved text index first.')
    original=streams.folder(root,index['source_id'])/'source.bin'
    sig={name:{**indexes._signature(path),'ctime_ns':path.stat().st_ctime_ns} for name,path in
         [('database',folder/'records.sqlite3'),('original',original)]}
    if sig['original']['bytes']!=index['source_bytes'] or (full and file_digest(original)!=index['source_sha256']):raise ValueError('Original source integrity changed.')
    return index,sig,permissions.snapshot(root,index)


def _state(connection):
    record=json.loads(connection.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
    if (record.get('format')!='almg-stream-character-bpe-fit-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
            or record.get('status') not in ('alphabet','counting','awaiting_publication')
            or record.get('model_training_enabled') is not False or record.get('release_approved') is not False
            or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})):
        raise ValueError('Whole-split character BPE progress integrity check failed.')
    return record


def _write(connection,record):
    record={k:v for k,v in record.items() if k!='revision'};record['revision']=digest(record)
    connection.execute('UPDATE state SET value=? WHERE id=1',(json.dumps(record),));return record


def review(root,index_id,cap=128):
    if type(cap) is not int or not 32<=cap<=512:raise ValueError('This whole-split baseline supports vocabulary cap 32 to 512 only.')
    try:index,signatures,permission=_binding(root,index_id,True)
    except (OSError,sqlite3.Error) as error:raise ValueError('Restore the verified original source/index before whole-split fitting.') from error
    if not index['split_counts']['train']:raise ValueError('The saved index requires a nonempty training split.')
    result={'format':'almg-stream-character-bpe-fit-review-v1','schema_version':1,'index_id':index_id,'index_revision':index['revision'],
            'source_provenance':{k:index[k] for k in ('source_id','source_name','source_sha256','source_bytes')},
            'source_signatures':signatures,'source_permission_review':permission,'vocabulary_cap':cap,
            'population_split_counts':index['split_counts'],'implementation_sha256':_implementation(),
            'scope':'all_unique_training_records_only_no_heldouts_no_occurrence_expansion',
            'algorithm':'freeze_complete_training_nfc_alphabet_then_global_character_pairs_frequency_2_lexicographic_ties',
            'maximum_learned_merges':511,'maximum_record_utf8_bytes':65536,'model_training_enabled':False}
    result['revision']=digest(result);return result


def begin(root,index_id,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm the reviewed whole-training-split character BPE.')
    if not isinstance(reviewed,dict) or reviewed!=review(root,index_id,reviewed.get('vocabulary_cap')):raise ValueError('The whole-split fitting review changed.')
    if shutil.disk_usage(root).free<64*1024*1024:raise ValueError('Whole-split character BPE fitting needs 64 MiB of free scratch space for bounded disk counters.')
    record={'format':'almg-stream-character-bpe-fit-v1','schema_version':1,'id':uuid.uuid4().hex,'status':'alphabet',
            'review':reviewed,'processed_records':0,'training_bytes':0,'last_group':'','training_chain_sha256':digest([]),
            'total_records':reviewed['population_split_counts']['train'],'implementation_sha256':_implementation(),
            'alphabet':[],'alphabet_counts':[],'merges':[],'merge_history':[],'completed_passes':0,'pass_chain_sha256':digest([]),'pass_bytes':0,
            'approval':{'version':1,'scope':'whole_training_split_tokenizer_fitting_only','review_revision':reviewed['revision'],
                        'confirmed_at':datetime.now(timezone.utc).isoformat()},'model_training_enabled':False,'release_approved':False}
    folder=_folder(root,record['id']);folder.mkdir(parents=True)
    with indexes._connect(folder/'work.sqlite3') as connection:
        connection.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        connection.execute('CREATE TABLE characters(character TEXT PRIMARY KEY,n INTEGER NOT NULL)')
        connection.execute('CREATE TABLE pairs(a INTEGER,b INTEGER,n INTEGER NOT NULL,PRIMARY KEY(a,b))')
        connection.execute('INSERT INTO state VALUES(1,?)',('{}',));record=_write(connection,record)
    return record


def read(root,identifier):
    try:
        folder=_folder(root,identifier)
        with indexes._connect(folder/'work.sqlite3',True) as connection:record=_state(connection)
        if record.get('id')!=identifier:raise ValueError('Whole-split fitting identifier changed.')
        if (folder/'artifacts').exists():
            path=folder/'artifacts';manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
            artifact=json.loads((path/'tokenizer.json').read_text(encoding='utf-8'));codec=StreamCharacterBPE.restore(artifact)
            if (record['status']!='awaiting_publication' or manifest.get('status')!='complete'
                    or manifest.get('job_revision')!=record['revision']
                    or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                    or manifest.get('files')!={'tokenizer.json':file_digest(path/'tokenizer.json')}
                    or manifest.get('tokenizer_sha256')!=digest(artifact)
                    or codec.alphabet!=record['alphabet'] or codec.vocabulary_size!=record['review']['vocabulary_cap'] or codec.merges!=manifest.get('learned_merges')
                    or len(codec.pieces)!=manifest.get('vocabulary_size')
                    or codec.training_sha256!=record['training_chain_sha256'] or codec.training_records!=record['total_records']
                    or any(manifest.get(k)!=v for k,v in record.items() if k not in ('status','revision'))):
                raise ValueError('Published whole-split BPE artifact integrity check failed.')
            return manifest
        return record
    except (OSError,sqlite3.Error,TypeError,KeyError) as error:raise ValueError('Whole-split character BPE fit is unavailable; preserve its files and restore verified storage.') from error


def _publish(root,record):
    folder=_folder(root,record['id'])
    merges=record['merges']
    codec=StreamCharacterBPE(record['alphabet'],merges,record['training_chain_sha256'],record['review']['vocabulary_cap'],record['total_records'])
    with TemporaryDirectory(prefix='.publish-',dir=folder) as temporary:
        staged=Path(temporary)/'artifacts';staged.mkdir()
        (staged/'tokenizer.json').write_text(json.dumps(codec.artifact(),ensure_ascii=False,indent=2),encoding='utf-8')
        manifest={k:v for k,v in record.items() if k!='revision'}
        manifest.update(status='complete',job_revision=record['revision'],vocabulary_size=len(codec.pieces),
                        tokenizer_sha256=digest(codec.artifact()),learned_merges=merges,
                        pair_frequency=None if not merges else record['merge_history'][-1]['frequency'],files={'tokenizer.json':file_digest(staged/'tokenizer.json')})
        manifest['revision']=digest(manifest)
        (staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        staged.rename(folder/'artifacts')
    return read(root,record['id'])


def step(root,identifier,confirmed):
    if confirmed is not True:raise ValueError('Confirm continuing the saved whole-split BPE fit.')
    with _LOCK:
        record=read(root,identifier)
        if record['status']=='complete':return record
        if record['implementation_sha256']!=_implementation():raise ValueError('Fitting implementation changed. Preserve progress and start a newly reviewed fit.')
        approved=record['review'];index_id=approved['index_id']
        try:
            index,sig,permission=_binding(root,index_id,False)
            if index['revision']!=approved['index_revision'] or sig!=approved['source_signatures'] or permission!=approved['source_permission_review']:
                raise ValueError('Source or permissions changed; saved fitting progress is preserved.')
            if record['status']=='awaiting_publication':
                if review(root,index_id,approved['vocabulary_cap'])!=approved:raise ValueError('Publication source binding changed.')
                return _publish(root,record)
            folder=_folder(root,identifier);processed=bytes_read=0
            discovering=record['status']=='alphabet'
            codec=None if discovering else StreamCharacterBPE(record['alphabet'],record['merges'],record['training_chain_sha256'],approved['vocabulary_cap'],record['total_records'])
            with indexes._connect(folder/'work.sqlite3') as work, indexes._connect(indexes._folder(root,index_id)/'records.sqlite3',True) as source:
                work.execute('BEGIN IMMEDIATE');record=_state(work)
                cursor=source.execute('SELECT group_sha256,text FROM documents WHERE split=? AND group_sha256>? ORDER BY group_sha256',('train',record['last_group']))
                while processed<MAX_BATCH_RECORDS and bytes_read<MAX_BATCH_BYTES:
                    row=cursor.fetchone()
                    if row is None:break
                    group,text=row
                    if digest(text)!=group:raise ValueError('Training record content no longer matches its saved group.')
                    normalized,encoded=StreamCharacterBPE.normalized(text)
                    if discovering:
                        work.executemany('INSERT INTO characters VALUES(?,?) ON CONFLICT(character) DO UPDATE SET n=n+excluded.n',Counter(normalized).items())
                        if work.execute('SELECT COUNT(*) FROM characters').fetchone()[0]>approved['vocabulary_cap']:
                            raise ValueError('Training alphabet exceeds the reviewed vocabulary cap. Preserve progress and review a larger budget; held-out text is never fitted.')
                    else:
                        tokens=codec.encode(text);pairs=Counter(zip(tokens,tokens[1:]))
                        work.executemany('INSERT INTO pairs VALUES(?,?,?) ON CONFLICT(a,b) DO UPDATE SET n=n+excluded.n',
                                         ((a,b,n) for (a,b),n in pairs.items()))
                    record['pass_chain_sha256']=digest({'previous':record['pass_chain_sha256'],'group_sha256':group})
                    record['processed_records']+=1;record['pass_bytes']+=len(encoded);record['last_group']=group
                    processed+=1;bytes_read+=len(encoded)
                complete=source.execute('SELECT 1 FROM documents WHERE split=? AND group_sha256>? LIMIT 1',('train',record['last_group'])).fetchone() is None
                current,current_sig,current_permission=_binding(root,index_id,complete)
                if current!=index or current_sig!=sig or current_permission!=permission:raise ValueError('Source changed during fitting; saved progress is preserved.')
                if complete:
                    if record['processed_records']!=record['total_records']:raise ValueError('Training population mismatch; publication blocked.')
                    if discovering:
                        values=work.execute('SELECT character,n FROM characters ORDER BY character').fetchall()
                        record['alphabet']=[char for char,n in values];record['alphabet_counts']=[n for char,n in values]
                        record['training_chain_sha256']=record['pass_chain_sha256'];record['training_bytes']=record['pass_bytes']
                        record['status']='counting' if len(values)<approved['vocabulary_cap'] else 'awaiting_publication'
                    else:
                        if record['pass_chain_sha256']!=record['training_chain_sha256'] or record['pass_bytes']!=record['training_bytes']:
                            raise ValueError('Training population changed after alphabet discovery.')
                        best=work.execute('SELECT a,b,n FROM pairs ORDER BY n DESC,a,b LIMIT 1').fetchone()
                        if best and best[2]>=2 and len(record['alphabet'])+len(record['merges'])<approved['vocabulary_cap']:
                            if len((codec.pieces[best[0]]+codec.pieces[best[1]]).encode('utf-8'))>4096:
                                raise ValueError('Selected character token exceeds the 4096-byte piece limit. Preserve progress and review a smaller cap.')
                            record['merges'].append([best[0],best[1]])
                            record['merge_history'].append({'id':len(record['alphabet'])+len(record['merges'])-1,'pair':[best[0],best[1]],'frequency':best[2]})
                        else:record['status']='awaiting_publication'
                        record['completed_passes']+=1
                        if len(record['alphabet'])+len(record['merges'])>=approved['vocabulary_cap']:record['status']='awaiting_publication'
                    if record['status']=='counting':
                        work.execute('DELETE FROM pairs')
                        record.update(processed_records=0,last_group='',pass_chain_sha256=digest([]),pass_bytes=0)
                record=_write(work,record)
            return _publish(root,record) if record['status']=='awaiting_publication' else record
        except (OSError,sqlite3.Error) as error:raise ValueError('Fitting storage is unavailable; committed progress is preserved. Restore storage and explicitly resume.') from error


def list_fits(root,index_id):
    indexes.read(root,index_id);parent=Path(root)/'decoder-stream-character-bpe-fits';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['review']['index_id']==index_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def export(root,identifier,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm private whole-split tokenizer export.')
    record=read(root,identifier)
    if record['status']!='complete' or not isinstance(reviewed,dict) or reviewed!=record:raise ValueError('Review the completed whole-split tokenizer before export.')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json','tokenizer.json'):archive.writestr(name,(_folder(root,identifier)/'artifacts'/name).read_bytes())
    if read(root,identifier)!=record:raise ValueError('Whole-split tokenizer changed during export.')
    payload=buffer.getvalue();return {'name':f'whole-split-character-bpe-{identifier[:8]}.zip','bytes':len(payload),'data':base64.b64encode(payload).decode()}
