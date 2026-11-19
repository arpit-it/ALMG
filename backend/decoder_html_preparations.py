"""Explicit saved HTML inputs with stable publication identity and recovery."""
import json
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from . import decoder_html as html, decoder_datasets as datasets
    from .run_manifest import digest,file_digest
else:
    import decoder_html as html
    import decoder_datasets as datasets
    from run_manifest import digest,file_digest

_LOCK=threading.RLock()


def _folder(root,draft_id):
    # HTML drafts have their own namespace.
    if not isinstance(draft_id,str) or len(draft_id)!=32 or any(char not in '0123456789abcdef' for char in draft_id):
        raise ValueError('Invalid HTML preparation ID.')
    return Path(root)/'decoder-html-preparations'/draft_id


def _implementation():
    return digest({name:file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_html_preparations.py','decoder_html.py','decoder_datasets.py')})


def _write(folder,record):
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(folder/'record.json')
    finally:temporary.unlink(missing_ok=True)


def _load(root,draft_id):
    folder=_folder(root,draft_id)
    try:
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        path=folder/'inputs.json'
        if path.stat().st_size>256000:raise ValueError('Saved HTML inputs exceed the supported bound.')
        inputs=json.loads(path.read_text(encoding='utf-8'))
        if (record.get('format')!='almg-html-preparation-v1' or type(record.get('schema_version')) is not int
                or record['schema_version']!=1 or record.get('id')!=draft_id or record.get('dataset_id')!=draft_id
                or record.get('status') not in ('awaiting_preparation','complete')
                or record.get('inputs_sha256')!=digest(inputs)):
            raise ValueError('Saved HTML preparation integrity check failed.')
        return record,inputs
    except (OSError,TypeError,KeyError) as error:raise ValueError('Saved HTML preparation is unavailable.') from error


def read(root,draft_id):
    record,inputs=_load(root,draft_id)
    if record['status']=='complete' and digest(datasets.read(root,draft_id))!=record['dataset_manifest_sha256']:
        raise ValueError('Completed HTML preparation dataset changed.')
    return {**record,'extraction_review':inputs['reviewed'],'implementation_current':record['implementation_sha256']==_implementation()}


def create(root,documents,confirmed,reviewed):
    if confirmed is not True:raise ValueError('Confirm saving reviewed original HTML inputs locally.')
    current=html.review(documents)
    if not isinstance(reviewed,dict) or reviewed!=current:raise ValueError('The HTML extraction review changed. Reopen it before saving.')
    inputs={'documents':documents,'reviewed':reviewed}
    draft_id=uuid.uuid4().hex
    record={'format':'almg-html-preparation-v1','schema_version':1,'id':draft_id,'dataset_id':draft_id,
            'status':'awaiting_preparation','inputs_sha256':digest(inputs),
            'implementation_sha256':_implementation(),'input_documents':len(documents),
            'extraction_review_revision':reviewed['revision'],'policy':'explicit_resume_only_no_training'}
    parent=Path(root)/'decoder-html-preparations';parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.html-',dir=parent) as temporary:
        staged=Path(temporary)/'draft';staged.mkdir()
        (staged/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False),encoding='utf-8')
        _write(staged,record);staged.rename(parent/draft_id)
    return read(root,draft_id)


def resume(root,draft_id,confirmed):
    if confirmed is not True:raise ValueError('Confirm preparing the saved HTML inputs.')
    with _LOCK:
        record,inputs=_load(root,draft_id)
        if record['status']=='complete':
            read(root,draft_id)
            return datasets.read(root,draft_id)
        if record['implementation_sha256']!=_implementation():raise ValueError('HTML preparation implementation changed; preserve this draft and start a newly reviewed preparation.')
        if (Path(root)/'decoder-datasets'/draft_id).exists():
            dataset=datasets.read(root,draft_id)
            if dataset.get('derivation',{}).get('extraction_review_revision')!=record['extraction_review_revision']:
                raise ValueError('Existing HTML dataset does not match the saved extraction review.')
        else:
            dataset=html.prepare(root,inputs['documents'],True,inputs['reviewed'],_dataset_id=draft_id)
        record.update(status='complete',dataset_manifest_sha256=digest(dataset))
        _write(_folder(root,draft_id),record)
        return dataset


def list_drafts(root):
    parent=Path(root)/'decoder-html-preparations';result=[]
    for folder in sorted(parent.iterdir()) if parent.exists() else []:
        if folder.name.startswith('.'):continue
        try:result.append(read(root,folder.name))
        except ValueError:continue
    return result[-20:]
