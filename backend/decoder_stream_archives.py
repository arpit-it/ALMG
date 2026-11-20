"""Explicit private export of passing streamed checkpoints; no release or import."""
import base64
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
import zipfile
if __package__:
    from . import decoder_stream_evaluations as evaluations, decoder_stream_previews as previews, decoder_stream_training as training, decoder_bundle
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_evaluations as evaluations, decoder_stream_previews as previews, decoder_stream_training as training, decoder_bundle
    from run_manifest import digest,file_digest
FORMAT='almg-private-stream-decoder-export-v1'


def _material(root,run_id,revision):
    state=evaluations._validated(root,run_id,revision)
    saved=evaluations.list_reports(root,run_id,True,revision)
    candidates=previews.list_previews(root,run_id,True,revision)
    if not saved or not candidates:raise ValueError('Save an independent CPU evaluation and private preview before export.')
    passing=[record for record in saved if record.get('passed') is True]
    if not passing:raise ValueError('The saved streamed decoder does not meet its 80% evaluation target; private export is unavailable.')
    fresh=evaluations.evaluate(root,run_id,True,revision,persist=False)
    evaluation=passing[-1];preview=candidates[-1]
    if fresh['passed'] is not True or digest(fresh['evaluation'])!=digest(evaluation['evaluation']):raise ValueError('The independent evaluation no longer reproduces; evaluate again before export.')
    repeated=previews.preview(root,run_id,True,revision,preview['prompt'],preview['inference']['max_new_tokens'],persist=False)
    if any(preview.get(key)!=repeated[key] for key in ('prompt_token_ids','generated_token_ids','completion','text','checkpoint_manifest_sha256','tokenizer_sha256')):
        raise ValueError('The saved preview no longer reproduces; preview again before export.')
    folder=training._folder(root,run_id)/state['checkpoint'];decoder_bundle.load(folder)
    contents={f'bundle/{name}':(folder/name).read_bytes() for name in ('decoder.json','tokenizer.json','manifest.json')}
    manifest=json.loads(contents['bundle/manifest.json'])
    if (hashlib.sha256(contents['bundle/manifest.json']).hexdigest()!=state['checkpoint_manifest_sha256']
            or any(hashlib.sha256(contents['bundle/'+key]).hexdigest()!=value for key,value in manifest['files'].items())):
        raise ValueError('Checkpoint files changed during export review.')
    contents.update({'evaluation.json':json.dumps(evaluation,ensure_ascii=False,allow_nan=False,indent=2).encode(),
                     'preview.json':json.dumps(preview,ensure_ascii=False,allow_nan=False,indent=2).encode()})
    if sum(map(len,contents.values()))>8*1024*1024:raise ValueError('Private streamed export exceeds its bounded archive limit.')
    if evaluations._validated(root,run_id,revision)!=state:raise ValueError('Trial/source bindings changed during export review.')
    review={'format':FORMAT,'schema_version':1,'run_id':run_id,'run_revision':revision,'checkpoint_manifest_sha256':state['checkpoint_manifest_sha256'],
            'evaluation_revision':evaluation['revision'],'preview_revision':preview['revision'],
            'files':{name:hashlib.sha256(data).hexdigest() for name,data in contents.items()},
            'evaluation_verified':True,'preview_reproduced':True,'release_approved':False,
            'scope':'private_experimental_checkpoint_with_saved_codec_and_receipts_no_source_documents_or_release',
            'implementation_sha256':file_digest(Path(__file__))}
    review['revision']=digest(review)
    return review,contents


def review(root,run_id,confirmed,reviewed_revision):
    if confirmed is not True:raise ValueError('Confirm review of a private model archive containing weights, tokenizer pieces and saved prompt/output.')
    return _material(root,run_id,reviewed_revision)[0]


def export(root,run_id,confirmed,reviewed_revision,approved_review):
    if confirmed is not True:raise ValueError('Confirm saving the reviewed private streamed-model archive.')
    current,contents=_material(root,run_id,reviewed_revision)
    if current!=approved_review:raise ValueError('Private export review changed; reopen the exact review.')
    identifier=uuid.uuid4().hex;envelope={'format':FORMAT,'schema_version':1,'id':identifier,'approved_review':current,'release_approved':False}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():archive.writestr(name,data)
        archive.writestr('export-manifest.json',json.dumps(envelope,ensure_ascii=False,allow_nan=False,indent=2))
    data=output.getvalue()
    if len(data)>8*1024*1024:raise ValueError('Private streamed archive is too large.')
    evaluations._validated(root,run_id,reviewed_revision)
    receipt={'format':FORMAT,'schema_version':1,'id':identifier,'run_id':run_id,'run_revision':reviewed_revision,
             'review_revision':current['revision'],'archive_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'release_approved':False}
    receipt['revision']=digest(receipt)
    parent=Path(root)/'decoder-stream-training-exports'/run_id;parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.export-',dir=parent) as temporary:
        staged=Path(temporary)/identifier;staged.mkdir();(staged/'bundle.zip').write_bytes(data)
        (staged/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');staged.rename(parent/identifier)
    return {'name':f'private-stream-decoder-{run_id[:8]}.zip','data':base64.b64encode(data).decode(),'receipt':receipt}
