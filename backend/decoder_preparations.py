"""Explicit, bounded local preparation drafts; never auto-resume or start training."""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import threading
import uuid

if __package__:
    from . import decoder_datasets as datasets
    from .run_manifest import digest, file_digest
else:
    import decoder_datasets as datasets
    from run_manifest import digest, file_digest

_LOCK = threading.RLock()


def implementation():
    return digest({name: file_digest(Path(__file__).with_name(name))
                   for name in ('decoder_preparations.py', 'decoder_datasets.py')})


def folder(root, draft_id):
    if not isinstance(draft_id, str) or not re.fullmatch('[a-f0-9]{32}', draft_id):
        raise ValueError('Invalid local preparation draft ID.')
    return Path(root) / 'decoder-preparations' / draft_id


def _write_record(path, record):
    temporary = path / (uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path / 'record.json')
    finally:
        temporary.unlink(missing_ok=True)


def create(root, documents, confirmed, tokenizer_kind='words'):
    if confirmed is not True:
        raise ValueError('Confirm saving original local inputs for later preparation.')
    # Reuse the production validator/tokenizer in a disposable workspace, without
    # publishing a dataset or transferring any training approval.
    with TemporaryDirectory(prefix='almg-draft-validation-') as temporary:
        preview = datasets.prepare(temporary, documents, True, tokenizer_kind)
    inputs = {'documents': documents, 'tokenizer_kind': tokenizer_kind}
    draft_id = uuid.uuid4().hex
    record = {'format': 'almg-decoder-preparation-v1', 'schema_version': 1,
              'id': draft_id, 'status': 'awaiting_preparation', 'inputs_sha256': digest(inputs),
              'implementation_sha256': implementation(), 'dataset_id': draft_id,
              'input_documents': preview['input_documents'], 'unique_documents': preview['unique_documents'],
              'tokenizer_kind': tokenizer_kind, 'policy': 'explicit_resume_only_no_training'}
    directory = Path(root) / 'decoder-preparations'
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.draft-', dir=directory) as temporary:
        staged = Path(temporary) / 'draft'
        staged.mkdir()
        (staged / 'inputs.json').write_text(json.dumps(inputs, ensure_ascii=False), encoding='utf-8')
        _write_record(staged, record)
        staged.rename(directory / draft_id)
    return read(root, draft_id)


def _load(root, draft_id):
    path = folder(root, draft_id)
    try:
        record = json.loads((path / 'record.json').read_text(encoding='utf-8'))
        inputs = json.loads((path / 'inputs.json').read_text(encoding='utf-8'))
        if (record.get('format') != 'almg-decoder-preparation-v1'
                or type(record.get('schema_version')) is not int or record['schema_version'] != 1
                or record.get('id') != draft_id or record.get('dataset_id') != draft_id
                or record.get('status') not in ('awaiting_preparation', 'complete')
                or digest(inputs) != record.get('inputs_sha256')):
            raise ValueError('Local preparation draft integrity check failed.')
        return record, inputs
    except (OSError, TypeError, KeyError, AttributeError) as error:
        raise ValueError('Local preparation draft is unavailable or incomplete.') from error


def read(root, draft_id):
    record, _ = _load(root, draft_id)
    if record['status'] == 'complete':
        if digest(datasets.read(root, record['dataset_id'])) != record.get('dataset_manifest_sha256'):
            raise ValueError('The completed preparation dataset changed.')
    return {**record, 'implementation_current': record['implementation_sha256'] == implementation()}


def list_drafts(root):
    directory = Path(root) / 'decoder-preparations'
    records = []
    for path in sorted(directory.iterdir()) if directory.exists() else []:
        if path.name.startswith('.'):
            continue
        try:
            records.append(read(root, path.name))
        except ValueError:
            continue
    return records[-20:]


def resume(root, draft_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm preparation of the saved local inputs.')
    with _LOCK:
        record, inputs = _load(root, draft_id)
        if record['status'] == 'complete':
            read(root, draft_id)
            return datasets.read(root, record['dataset_id'])
        if record['implementation_sha256'] != implementation():
            raise ValueError('Preparation implementation changed. Preserve this draft and reselect inputs for a new review.')
        binding = {'version': 1, 'operation': 'saved_local_preparation', 'draft_id': draft_id,
                   'inputs_sha256': record['inputs_sha256'], 'implementation_sha256': record['implementation_sha256']}
        destination = Path(root) / 'decoder-datasets' / draft_id
        if destination.exists():
            dataset = datasets.read(root, draft_id)
            if dataset.get('derivation') != binding:
                raise ValueError('Existing dataset does not match the saved preparation draft.')
        else:
            dataset = datasets.prepare(root, inputs['documents'], True, inputs['tokenizer_kind'],
                                       _derivation=binding, _dataset_id=draft_id)
        record.update(status='complete', dataset_manifest_sha256=digest(dataset))
        _write_record(folder(root, draft_id), record)
        return dataset
