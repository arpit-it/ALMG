"""Durable explicitly approved generated-text decoder trials, separate from jobs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
import uuid

if __package__:
    from . import decoder_training, recipe_contracts, run_manifest
else:
    import decoder_training, recipe_contracts, run_manifest

_LOCK = threading.Lock()
_ACTIVE = set()
_CANCEL = {}


def specification():
    return {'recipe': 'decoder_from_scratch', 'recipe_version': 1, 'approach': 'from_scratch',
            'scope': 'generated_local_text_fixture', 'stage_version': 1,
            'components': {name: run_manifest.file_digest(Path(__file__).with_name(name)) for name in
                           ('decoder_trials.py', 'decoder_training.py', 'decoder_recipe.py', 'decoder_tokenizer.py',
                            'decoder_checkpoint.py', 'decoder_bundle.py')}}


def folder(root, trial_id):
    if not isinstance(trial_id, str) or not re.fullmatch('[a-f0-9]{32}', trial_id):
        raise ValueError('Invalid decoder trial ID.')
    return Path(root) / 'decoder-trials' / trial_id


def write(root, record):
    path = folder(root, record['id'])
    path.mkdir(parents=True, exist_ok=True)
    temporary = path / 'record.tmp'
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path / 'record.json')


def read(root, trial_id):
    try:
        record = json.loads((folder(root, trial_id) / 'record.json').read_text(encoding='utf-8'))
        if (type(record.get('schema_version')) is not int or record['schema_version'] != 1 or record.get('id') != trial_id
                or not isinstance(record.get('created_at'), str)
                or record.get('status') not in ('queued', 'running', 'interrupted', 'complete')):
            raise ValueError('Unsupported decoder trial record.')
        return record
    except (OSError, TypeError, AttributeError) as error:
        raise ValueError('Decoder trial record is unavailable or unreadable.') from error


def list_trials(root, limit=20):
    directory = Path(root) / 'decoder-trials'
    records = []
    if directory.exists():
        for path in directory.iterdir():
            if re.fullmatch('[a-f0-9]{32}', path.name):
                try:
                    records.append(read(root, path.name))
                except ValueError:
                    continue
    return sorted(records, key=lambda record: record.get('created_at', ''), reverse=True)[:limit]


def recover(root):
    """A restarted backend never resumes work without renewed approval."""
    for record in list_trials(root, limit=None):
        with _LOCK:
            if (str(Path(root)), record['id']) not in _ACTIVE and record.get('status') in ('queued', 'running'):
                record.update(status='interrupted', error='Backend stopped. Review the saved trial and approve resume.')
                write(root, record)


def cancel(root, trial_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm cancellation of this saved trial.')
    key = (str(Path(root)), trial_id)
    with _LOCK:
        record = read(root, trial_id)
        if record['status'] not in ('queued', 'running') or key not in _CANCEL:
            raise ValueError('Only an active saved trial can be cancelled.')
        _CANCEL[key].set()
        record.update(cancel_requested=True, error='Cancellation requested; waiting for the next training boundary.')
        write(root, record)
    return record


def execute(root, trial_id):
    key = (str(Path(root)), trial_id)
    try:
        with _LOCK:
            record = read(root, trial_id)
            stop_event = _CANCEL[key]
            if (record.get('specification') != specification()
                    or record.get('approval', {}).get('revision') != run_manifest.digest(record.get('specification'))):
                raise ValueError('Saved decoder trial approval no longer matches this implementation. Approve a new trial.')
            if stop_event.is_set():
                raise decoder_training.Cancelled('Cancelled before training. Approve resume to continue.')
            record.update(status='running', error=None, artifact_directory=str(folder(root, trial_id) / 'artifacts'))
            write(root, record)
        result = decoder_training.run(recipe_contracts.initialize_recipe,
                                      work_directory=folder(root, trial_id) / 'artifacts', stop=stop_event.is_set)
        with _LOCK:
            record = read(root, trial_id)
            if stop_event.is_set():
                record.update(status='interrupted', interruption_reason='user_cancelled',
                              error='Cancelled; any completed artifacts are preserved. Approve a new trial if a complete bundle exists.')
            else:
                record.update(status='complete', result=result, artifact_directory=str(folder(root, trial_id) / 'artifacts'))
            write(root, record)
    except Exception as error:
        with _LOCK:
            record = read(root, trial_id)
            record.update(status='interrupted', error=str(error))
            if isinstance(error, decoder_training.Cancelled):
                record['interruption_reason'] = 'user_cancelled'
            write(root, record)
    finally:
        with _LOCK:
            _ACTIVE.discard(key)
            _CANCEL.pop(key, None)


def start(root, confirmed, submit, trial_id=None):
    if confirmed is not True:
        raise ValueError('Approve the generated-text decoder trial before starting it.')
    spec = specification()
    with _LOCK:
        if trial_id is None:
            trial_id = uuid.uuid4().hex
            record = {'schema_version': 1, 'id': trial_id, 'created_at': datetime.now(timezone.utc).isoformat()}
        else:
            record = read(root, trial_id)
            if record.get('status') != 'interrupted' or (str(Path(root)), trial_id) in _ACTIVE:
                raise ValueError('Only an interrupted decoder trial can be resumed.')
            if record.get('specification') != spec:
                raise ValueError('Decoder trial implementation changed. Approve a new trial instead.')
            if (folder(root, trial_id) / 'artifacts' / 'bundle').exists():
                raise ValueError('A complete bundle already exists. Preserve it and approve a new trial instead.')
        if record.get('approval') is not None:
            record.setdefault('previous_approvals', []).append(record['approval'])
        record.update(status='queued', error=None, cancel_requested=False, interruption_reason=None, specification=spec,
                      approval={'id': uuid.uuid4().hex, 'confirmed_at': datetime.now(timezone.utc).isoformat(),
                                'revision': run_manifest.digest(spec)})
        write(root, record)
        _ACTIVE.add((str(Path(root)), trial_id))
        _CANCEL[(str(Path(root)), trial_id)] = threading.Event()
    try:
        submit(execute, root, trial_id)
    except Exception:
        with _LOCK:
            _ACTIVE.discard((str(Path(root)), trial_id))
            _CANCEL.pop((str(Path(root)), trial_id), None)
        record.update(status='interrupted', error='Worker could not start. Review and approve resume.')
        write(root, record)
        raise
    return record
