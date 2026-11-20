"""Approved bounded tokenizer fitting and split comparison; no pretraining integration."""
import base64
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid
import zipfile

if __package__:
    from . import decoder_datasets as datasets
    from .decoder_bpe import ByteBPE
    from .decoder_character_bpe import CharacterBPE
    from .decoder_unigram import UnigramTokenizer
    from .decoder_special_tokens import SpecialTokenizer,definitions,restore_base
    from .run_manifest import digest,file_digest
else:
    import decoder_datasets as datasets
    from decoder_bpe import ByteBPE
    from decoder_character_bpe import CharacterBPE
    from decoder_unigram import UnigramTokenizer
    from decoder_special_tokens import SpecialTokenizer,definitions,restore_base
    from run_manifest import digest,file_digest


def _folder(root,identifier):
    if not isinstance(identifier,str) or re.fullmatch('[a-f0-9]{32}',identifier) is None:raise ValueError('Invalid tokenizer experiment ID.')
    return Path(root)/'decoder-tokenizer-experiments'/identifier


def _config(config):
    if (not isinstance(config,dict) or 'vocabulary_cap' not in config
            or not set(config)<={'vocabulary_cap','algorithm','special_tokens','unknown_policy'}):raise ValueError('Choose supported tokenizer configuration fields.')
    algorithm=config.get('algorithm','byte_level_bpe')
    if algorithm not in ('byte_level_bpe','character_bpe','unigram'):raise ValueError('Unsupported tokenizer algorithm.')
    labels=definitions(config.get('special_tokens',{}));policy=config.get('unknown_policy','reject')
    if policy not in ('reject','replace') or (policy=='replace' and 'unk' not in labels):raise ValueError('Unknown replacement requires an explicit UNK token.')
    minimum=256 if algorithm=='byte_level_bpe' else 32;cap=config['vocabulary_cap']
    if type(cap) is not int or not minimum+len(labels)<=cap<=512:raise ValueError('The vocabulary cap must include all reserved special IDs and the base alphabet.')
    return algorithm,cap,labels,policy


def compare(rows,model,algorithm):
    comparison={}
    for split in ('train','validation','test'):
        selected=[row for row in rows if row['split']==split]
        byte_tokens=token_count=characters=encoded_documents=encoded_bytes=uncovered=0
        lossless_documents=lossless_tokens=lossless_bytes=lossless_characters=unknown_count=boundary_count=0
        for row in selected:
            text,encoded=model.normalized(row['text']);characters+=len(text);byte_tokens+=len(encoded)
            missing=model.uncovered(text) if hasattr(model,'uncovered') else 0;uncovered+=missing
            if missing and getattr(model,'unknown_policy','reject')!='replace':continue
            tokens=model.encode(text);decoded=model.decode(tokens)
            if not missing:
                if decoded!=text:raise ValueError('Tokenizer lossless round-trip validation failed; no artifact published.')
                lossless_documents+=1;lossless_tokens+=len(tokens);lossless_bytes+=len(encoded);lossless_characters+=len(text)
            ids=getattr(model,'special_ids',{})
            unknown_count+=sum(token==ids.get('unk') for token in tokens)
            boundary_count+=sum(token in [ids[role] for role in ('bos','eos') if role in ids] for token in tokens)
            token_count+=len(tokens);encoded_documents+=1;encoded_bytes+=len(encoded)
        comparison[split]={'documents':len(selected),'documents_encoded':encoded_documents,'documents_lossless':lossless_documents,
                           'documents_lossy':encoded_documents-lossless_documents,'nfc_characters':characters,
                           'baseline_byte_tokens':byte_tokens,'encoded_baseline_byte_tokens':encoded_bytes,
                           'lossless_baseline_byte_tokens':lossless_bytes,'token_count':token_count if encoded_documents else None,
                           'lossless_token_count':lossless_tokens if lossless_documents else None,
                           'tokens_per_nfc_character':lossless_tokens/lossless_characters if lossless_characters else None,
                           'byte_to_token_ratio':lossless_bytes/lossless_tokens if lossless_tokens else None,
                           'uncovered_character_count':uncovered,'covered_character_fraction':(characters-uncovered)/characters if characters else None,
                           'unknown_tokens':unknown_count if encoded_documents==len(selected) else None,'boundary_tokens':boundary_count,
                           'round_trip_verified':lossless_documents==len(selected),
                           'comparison_scope':'lossless_only_efficiency_all_encoded_token_counts','used_for_fitting':split=='train'}
        if algorithm!='unigram':
            comparison[split].update(bpe_tokens=comparison[split]['token_count'],byte_to_bpe_token_ratio=comparison[split]['byte_to_token_ratio'])
    return comparison


def train(root,dataset_id,confirmed,reviewed,config):
    if confirmed is not True:raise ValueError('Confirm tokenizer fitting on the reviewed training split; model training stays disabled.')
    algorithm,cap,labels,policy=_config(config)
    tokenizer_type={'byte_level_bpe':ByteBPE,'character_bpe':CharacterBPE,'unigram':UnigramTokenizer}[algorithm]
    dataset=datasets.read(root,dataset_id)
    if not isinstance(reviewed,dict) or reviewed!=dataset:raise ValueError('The dataset review changed. Reopen it before fitting.')
    rows=[json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    training=[row['text'] for row in rows if row['split']=='train']
    model=tokenizer_type.fit(training,cap-len(labels))
    if labels:model=SpecialTokenizer(model,labels,policy)
    artifact=model.artifact()
    comparison=compare(rows,model,algorithm)
    if datasets.read(root,dataset_id)!=dataset:raise ValueError('Dataset changed during BPE fitting; no artifact published.')
    identifier=uuid.uuid4().hex
    manifest={'format':'almg-tokenizer-experiment-v1','schema_version':1,'id':identifier,
              'dataset_id':dataset_id,'dataset_manifest_sha256':digest(dataset),'dataset_sha256':dataset['dataset_sha256'],
              'config':config,'algorithm':algorithm,'special_tokens':{role:{'id':model.special_ids[role],'literal':label} for role,label in labels.items()},
              'unknown_policy':policy,'vocabulary_size':len(model.pieces),'baseline_vocabulary_size':256,
              'training_documents_sha256':model.training_sha256,'fit_source':'training_split_only',
              'training_sampling':'unique_records_once_no_mixture_weight_expansion','comparison':comparison,
              'approval':{'version':1,'confirmed_at':datetime.now(timezone.utc).isoformat(),
                          'dataset_manifest_sha256':digest(dataset),'config_sha256':digest(config),'scope':'tokenizer_fitting_only'},
              'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in
                  ('decoder_tokenizer_experiments.py','decoder_bpe.py','decoder_character_bpe.py','decoder_unigram.py','decoder_special_tokens.py','decoder_datasets.py')}),
              'tokenizer_sha256':digest(artifact),'files':{},'model_training_enabled':False,'release_approved':False,
              'limitations':'Bounded tokenizer experiment only. Learned tokens may encode private training phrases. UNK replacement is explicitly lossy and excluded from efficiency ratios. Model integration is unavailable. Unigram uses bounded fixed-candidate EM without vocabulary pruning or sampling.'}
    parent=Path(root)/'decoder-tokenizer-experiments';parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.bpe-',dir=parent) as temporary:
        staged=Path(temporary)/'experiment';staged.mkdir()
        (staged/'tokenizer.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
        manifest['files']={'tokenizer.json':file_digest(staged/'tokenizer.json')};manifest['revision']=digest(manifest)
        (staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');staged.rename(parent/identifier)
    return read(root,identifier)


def read(root,identifier):
    folder=_folder(root,identifier)
    try:
        if any((folder/name).stat().st_size>256000 for name in ('manifest.json','tokenizer.json')):raise ValueError('Tokenizer experiment exceeds its bound.')
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));artifact=json.loads((folder/'tokenizer.json').read_text(encoding='utf-8'))
        model=SpecialTokenizer.restore(artifact) if artifact.get('format')=='almg-special-tokenizer-v1' else restore_base(artifact)
        base=model.base if isinstance(model,SpecialTokenizer) else model
        algorithm={'almg-byte-bpe-tokenizer-v1':'byte_level_bpe','almg-character-bpe-tokenizer-v1':'character_bpe','almg-unigram-tokenizer-v1':'unigram'}[base.artifact()['format']]
        configured,cap,labels,policy=_config(manifest.get('config'))
        expected_specials={role:{'id':model.special_ids[role],'literal':label} for role,label in labels.items()} if labels else {}
        if (manifest.get('format')!='almg-tokenizer-experiment-v1' or type(manifest.get('schema_version')) is not int
                or manifest['schema_version']!=1 or manifest.get('id')!=identifier
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or manifest.get('files')!={'tokenizer.json':file_digest(folder/'tokenizer.json')}
                or manifest.get('tokenizer_sha256')!=digest(artifact) or manifest.get('vocabulary_size')!=len(model.pieces)
                or manifest.get('training_documents_sha256')!=model.training_sha256
                or manifest.get('algorithm')!=algorithm or type(manifest.get('vocabulary_size')) is not int
                or configured!=algorithm or cap!=model.vocabulary_size
                or labels!=getattr(model,'definitions',{}) or policy!=getattr(model,'unknown_policy','reject')
                or digest(manifest.get('special_tokens',expected_specials))!=digest(expected_specials) or manifest.get('unknown_policy',policy)!=policy
                or (algorithm=='unigram' and len(base.history)!=6)
                or manifest.get('model_training_enabled') is not False or manifest.get('release_approved') is not False):
            raise ValueError('Tokenizer experiment integrity check failed.')
        return manifest
    except (OSError,TypeError,KeyError,AttributeError) as error:raise ValueError('Tokenizer experiment is unavailable.') from error


def list_experiments(root,dataset_id):
    datasets.read(root,dataset_id);parent=Path(root)/'decoder-tokenizer-experiments';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:
            record=read(root,folder.name)
            if record['dataset_id']==dataset_id:result.append(record)
        except ValueError:continue
    return result[-20:]


def export(root,identifier,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm private tokenizer export; learned pieces can encode training phrases.')
    manifest=read(root,identifier)
    if not isinstance(reviewed,dict) or reviewed!=manifest:raise ValueError('The tokenizer export review changed.')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json','tokenizer.json'):archive.writestr(name,(_folder(root,identifier)/name).read_bytes())
    if read(root,identifier)!=manifest:raise ValueError('Tokenizer changed during export.')
    payload=buffer.getvalue()
    return {'name':f'tokenizer-experiment-{identifier[:8]}.zip','bytes':len(payload),'data':base64.b64encode(payload).decode()}
