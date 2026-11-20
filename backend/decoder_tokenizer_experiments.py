"""Approved bounded BPE fitting and split comparison; no pretraining integration."""
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
    from .run_manifest import digest,file_digest
else:
    import decoder_datasets as datasets
    from decoder_bpe import ByteBPE
    from run_manifest import digest,file_digest


def _folder(root,identifier):
    if not isinstance(identifier,str) or re.fullmatch('[a-f0-9]{32}',identifier) is None:raise ValueError('Invalid tokenizer experiment ID.')
    return Path(root)/'decoder-tokenizer-experiments'/identifier


def train(root,dataset_id,confirmed,reviewed,config):
    if confirmed is not True:raise ValueError('Confirm BPE fitting on the reviewed training split; model training stays disabled.')
    if not isinstance(config,dict) or set(config)!={'vocabulary_cap'}:raise ValueError('Choose only the supported BPE vocabulary cap.')
    ByteBPE([], '0'*64,config['vocabulary_cap'])
    dataset=datasets.read(root,dataset_id)
    if not isinstance(reviewed,dict) or reviewed!=dataset:raise ValueError('The dataset review changed. Reopen it before fitting.')
    rows=[json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    training=[row['text'] for row in rows if row['split']=='train']
    model=ByteBPE.fit(training,config['vocabulary_cap']);artifact=model.artifact()
    comparison={}
    for split in ('train','validation','test'):
        selected=[row for row in rows if row['split']==split];byte_tokens=bpe_tokens=characters=0
        for row in selected:
            text,encoded=model.normalized(row['text']);tokens=model.encode(text)
            if model.decode(tokens)!=text:raise ValueError('BPE round-trip validation failed; no artifact published.')
            byte_tokens+=len(encoded);bpe_tokens+=len(tokens);characters+=len(text)
        comparison[split]={'documents':len(selected),'nfc_characters':characters,'baseline_byte_tokens':byte_tokens,
                           'bpe_tokens':bpe_tokens,'tokens_per_nfc_character':bpe_tokens/characters if characters else None,
                           'byte_to_bpe_token_ratio':byte_tokens/bpe_tokens if bpe_tokens else None,
                           'unknown_tokens':0,'round_trip_verified':True,'used_for_fitting':split=='train'}
    if datasets.read(root,dataset_id)!=dataset:raise ValueError('Dataset changed during BPE fitting; no artifact published.')
    identifier=uuid.uuid4().hex
    manifest={'format':'almg-tokenizer-experiment-v1','schema_version':1,'id':identifier,
              'dataset_id':dataset_id,'dataset_manifest_sha256':digest(dataset),'dataset_sha256':dataset['dataset_sha256'],
              'config':config,'algorithm':'byte_level_bpe','vocabulary_size':len(model.pieces),'baseline_vocabulary_size':256,
              'training_documents_sha256':model.training_sha256,'fit_source':'training_split_only',
              'training_sampling':'unique_records_once_no_mixture_weight_expansion','comparison':comparison,
              'approval':{'version':1,'confirmed_at':datetime.now(timezone.utc).isoformat(),
                          'dataset_manifest_sha256':digest(dataset),'config_sha256':digest(config),'scope':'tokenizer_fitting_only'},
              'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in
                  ('decoder_tokenizer_experiments.py','decoder_bpe.py','decoder_datasets.py')}),
              'tokenizer_sha256':digest(artifact),'files':{},'model_training_enabled':False,'release_approved':False,
              'limitations':'Bounded tokenizer experiment only. Learned byte tokens may encode private training phrases. Special tokens, Unigram and model integration are unavailable.'}
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
        model=ByteBPE.restore(artifact)
        if (manifest.get('format')!='almg-tokenizer-experiment-v1' or type(manifest.get('schema_version')) is not int
                or manifest['schema_version']!=1 or manifest.get('id')!=identifier
                or manifest.get('revision')!=digest({k:v for k,v in manifest.items() if k!='revision'})
                or manifest.get('files')!={'tokenizer.json':file_digest(folder/'tokenizer.json')}
                or manifest.get('tokenizer_sha256')!=digest(artifact) or manifest.get('vocabulary_size')!=len(model.pieces)
                or manifest.get('training_documents_sha256')!=model.training_sha256
                or manifest.get('config')!={'vocabulary_cap':model.vocabulary_size}
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
