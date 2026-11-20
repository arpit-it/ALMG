"""Explicit CPU bundle persistence check for reviewed streams; zero optimizer updates."""
import json
from pathlib import Path
import uuid

if __package__:
    from . import decoder_stream_learned_windows as windows,decoder_stream_learned_batches as batches,decoder_bundle,recipe_contracts,training_resources
    from .decoder_stream_model_tokenizer import StreamModelTokenizer
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_learned_windows as windows,decoder_stream_learned_batches as batches,decoder_bundle,recipe_contracts,training_resources
    from decoder_stream_model_tokenizer import StreamModelTokenizer
    from run_manifest import digest,file_digest


def _folder(root,window_id):
    windows._folder(root,window_id)
    return Path(root)/'decoder-stream-persistence-checks'/window_id


def run(root,window_id,confirmed,reviewed,reviewed_batch,cursor=None):
    if confirmed is not True:raise ValueError('Confirm saving fresh model/tokenizer weights for a private zero-update persistence check.')
    batch=batches.read_batch(root,window_id,True,reviewed,cursor,'train',4)
    if reviewed_batch!=batch or not batch['rows']:raise ValueError('Reopen the exact nonempty inspected training batch before checking persistence.')
    current,codec=windows._sources(root,reviewed['comparison_id'],reviewed['overlap_id'],True)
    if current!=reviewed['reviewed_sources']:raise ValueError('Stream persistence source review changed.')
    approval={'version':1,'scope':'fresh_stream_model_persistence_only','windows_id':window_id,'windows_revision':reviewed['revision'],
              'tokenizer_sha256':reviewed['tokenizer_sha256'],'inspected_batch_sha256':digest(batch),'seed':7}
    selection={'windows_id':window_id,'windows_revision':reviewed['revision'],'fit_id':reviewed['fit_id'],'fit_revision':current['fit']['revision'],
               'index_id':reviewed['index_id'],'index_revision':reviewed['index_revision'],'source_sha256':reviewed['source_sha256'],
               'tokenizer_sha256':reviewed['tokenizer_sha256'],'approval_sha256':digest(approval)}
    tokenizer=StreamModelTokenizer(codec.artifact(),selection)
    resources=training_resources.check_size(len(json.dumps(tokenizer.artifact()).encode())+4*16*8,_folder(root,window_id))
    model=recipe_contracts.initialize_recipe('decoder_from_scratch',{'vocab_size':len(tokenizer.vocabulary),'seed':7})
    training={'kind':'stream_model_persistence_check','schema_version':1,'approval':approval,'approval_sha256':digest(approval),
              'optimizer_updates':0,'pretrained_weights_loaded':False,'model_training_approved':False,'release_approved':False}
    directory=_folder(root,window_id)/uuid.uuid4().hex;directory.mkdir(parents=True)
    manifest=decoder_bundle.save(directory/'bundle',model,tokenizer,training,pretraining_stage='initialization_check')
    loaded,restored,verified=decoder_bundle.load(directory/'bundle')
    import numpy as np
    expected=model.logits(batch['inputs']);actual=loaded.logits(batch['inputs']);error=float(np.max(np.abs(expected-actual)))
    if error!=0 or tokenizer.artifact()!=restored.artifact() or manifest!=verified:raise ValueError('Stream model/tokenizer persistence round trip changed its outputs or artifact.')
    group=batch['provenance'][0]['group']
    with windows.indexes._connect(windows.indexes._folder(root,reviewed['index_id'])/'records.sqlite3',True) as db:
        row=db.execute('SELECT text,split FROM documents WHERE group_sha256=?',(group,)).fetchone()
    if not row or row[1]!='train':raise ValueError('Persistence probe must use its inspected training source.')
    tokens=tokenizer.encode(row[0])
    if restored.encode(row[0])!=tokens or restored.decode(tokens)!=row[0]:raise ValueError('Restored stream tokenizer changed lossless training-record IDs.')
    preview_ids=tokens[:min(16,len(tokens))];preview=restored.decode_preview(preview_ids)
    if batches.read_batch(root,window_id,True,reviewed,cursor,'train',4)!=batch:raise ValueError('Source bindings changed during persistence; private unpublished artifacts are preserved.')
    record={'format':'almg-stream-model-persistence-check-v1','schema_version':1,'id':directory.name,
            'windows_id':window_id,'windows_revision':reviewed['revision'],'tokenizer_kind':reviewed['fit_kind'],
            'vocabulary_size':len(tokenizer.vocabulary),'architecture_version':manifest['stages']['architecture'],
            'tokenization_version':manifest['stages']['tokenization'],'bundle_manifest_sha256':file_digest(directory/'bundle'/'manifest.json'),
            'tokenizer_sha256':tokenizer.fingerprint(),'source_codec_sha256':reviewed['tokenizer_sha256'],'inspected_batch_sha256':digest(batch),
            'probe_group':group,'probe_token_count':len(tokens),'preview_ids':preview_ids,'preview_text':preview,
            'cpu_logit_max_error':error,'all_parameter_tensors_equal':all(np.array_equal(model.parameters[key],loaded.parameters[key]) for key in model.parameters),
            'resources':resources,'optimizer_updates':0,'weight_origin':'newly_initialized','pretrained_weights_loaded':False,
            'model_training_approved':False,'release_approved':False,'model_quality_established':False,
            'scope':'private_fresh_model_bundle_roundtrip_only'}
    record['revision']=digest(record)
    temporary=directory/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8');temporary.replace(directory/'report.json')
    finally:temporary.unlink(missing_ok=True)
    return record


def list_reports(root,window_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm review of private stream persistence reports.')
    parent=_folder(root,window_id);result=[]
    for directory in sorted(parent.iterdir()) if parent.exists() else []:
        try:
            windows._folder(root,directory.name)
            path=directory/'report.json'
            if path.stat().st_size>256000:continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if (record.get('format')!='almg-stream-model-persistence-check-v1' or type(record.get('schema_version')) is not int or record['schema_version']!=1
                    or record.get('id')!=directory.name or record.get('windows_id')!=window_id
                    or record.get('revision')!=digest({k:v for k,v in record.items() if k!='revision'})
                    or record.get('bundle_manifest_sha256')!=file_digest(directory/'bundle'/'manifest.json')
                    or record.get('optimizer_updates')!=0 or any(record.get(key) is not False for key in ('pretrained_weights_loaded','model_training_approved','release_approved','model_quality_established'))):continue
            model,tokenizer,manifest=decoder_bundle.load(directory/'bundle')
            if tokenizer.fingerprint()!=record['tokenizer_sha256'] or manifest['stages']['tokenization']!=3:continue
            result.append(record)
        except (OSError,ValueError,TypeError,KeyError):continue
    return result[-20:]
