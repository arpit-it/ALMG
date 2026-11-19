"""Versioned local evidence for completed candidates; never loads model weights."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
from importlib.metadata import PackageNotFoundError, version


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()



class ApprovalChanged(ValueError):
    """Approved training inputs changed while waiting for execution."""


def approval_binding(job, rows, recipe_metadata):
    return {'job_id': job['id'], 'goal': job.get('prompt'), 'mode': job.get('mode'),
            'labels': deepcopy(job.get('plan', {}).get('labels', [])),
            'recipe': deepcopy(recipe_metadata), 'prepared_dataset_sha256': digest(rows),
            'prepared_rows': len(rows)}


def approve(job, rows, recipe_metadata):
    """Called only by the explicit training-approval route, never on restore."""
    from datetime import datetime, timezone
    import uuid
    binding = approval_binding(job, rows, recipe_metadata)
    return {'schema_version': 1, 'origin': 'explicit_training_approval',
            'approval_id': uuid.uuid4().hex, 'confirmed_at': datetime.now(timezone.utc).isoformat(),
            'revision': digest(binding), 'binding': binding}


def validate_approval(job, rows, recipe_metadata):
    receipt = job.get('training_approval')
    if receipt is None:
        return  # Legacy queued fixtures/jobs have no historical receipt to invent.
    try:
        if (type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
                or receipt['origin'] != 'explicit_training_approval'
                or not isinstance(receipt['approval_id'], str) or len(receipt['approval_id']) != 32
                or receipt['revision'] != digest(receipt['binding'])
                or receipt['binding'] != approval_binding(job, rows, recipe_metadata)):
            raise ValueError('changed')
    except (KeyError, TypeError, ValueError) as error:
        raise ApprovalChanged('Approved recipe, settings or dataset changed. Review the prepared dataset and approve training again.') from error


def build(job, rows, metrics, model_path, recipe_metadata):
    """Capture the runtime at candidate completion, not later at export time."""
    dependencies = {}
    for package in ('numpy', 'scikit-learn', 'joblib', 'Pillow'):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    partitions = {}
    for index, row in enumerate(rows):
        part = row.get('split', 'unspecified')
        partitions.setdefault(part, []).append({'index': index, 'row_sha256': digest(row),
                                               'group': row.get('group')})
    components = {}
    for name in ('studio.py', 'recipe_contracts.py', 'image_recipe.py', 'run_manifest.py'):
        components[name] = {'source_sha256': file_digest(Path(__file__).with_name(name))}
    approval = deepcopy(job.get('training_approval', {'origin': 'legacy_unrecorded'}))
    return {'schema_version': 1, 'capture': 'candidate_completion', 'job_id': job['id'],
            'recipe': deepcopy(recipe_metadata), 'settings_sha256': digest(recipe_metadata),
            'approval': approval, 'approval_sha256': digest(approval),
            'dataset': {'rows': len(rows), 'sha256': digest(rows)},
            'partitions': {name: {'rows': len(items), 'sha256': digest(items)}
                           for name, items in partitions.items()},
            'evaluation': deepcopy(metrics), 'evaluation_sha256': digest(metrics),
            'randomness': {'split_seed': metrics.get('split_seed'),
                           'note': 'Classifier estimators retain their existing default random_state; bitwise reproducibility is not guaranteed.'
                           if job.get('recipe', 'classifier') == 'classifier'
                           else 'Existing image fit is deterministic; no random seed is consumed.'},
            'runtime': {'python': platform.python_version(), 'system': platform.system(),
                        'machine': platform.machine(), 'processor': platform.processor(),
                        'training_device': 'CPU', 'dependencies': dependencies},
            'components': components,
            'artifact': {'name': Path(model_path).name, 'sha256': file_digest(model_path)}}


def write(folder, manifest):
    path = Path(folder) / 'run-manifest.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def read(folder):
    """Verify the stored candidate/release file without deserializing its weights."""
    folder = Path(folder)
    try:
        manifest = json.loads((folder / 'run-manifest.json').read_text(encoding='utf-8'))
        if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
            raise ValueError('Unsupported run manifest version.')
        artifact = manifest['artifact']
        if artifact['name'] not in ('candidate.json', 'candidate.joblib', 'model.json', 'model.joblib'):
            raise ValueError('Invalid run manifest artifact.')
        if file_digest(folder / artifact['name']) != artifact['sha256']:
            raise ValueError('Model file does not match the run manifest.')
        for field, hash_key in (('recipe', 'settings_sha256'), ('evaluation', 'evaluation_sha256')):
            if digest(manifest[field]) != manifest[hash_key]:
                raise ValueError('Run manifest metadata does not match its recorded hash.')
        if 'approval' in manifest and digest(manifest['approval']) != manifest.get('approval_sha256'):
            raise ValueError('Approval receipt does not match its recorded hash.')
        dataset_path = folder / ('dataset.json' if artifact['name'].startswith('candidate.') else 'dataset.jsonl')
        if dataset_path.suffix == '.json':
            rows = json.loads(dataset_path.read_text(encoding='utf-8'))
        else:
            rows = [json.loads(line) for line in dataset_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if digest(rows) != manifest['dataset']['sha256']:
            raise ValueError('Dataset file does not match the run manifest.')
        return manifest
    except FileNotFoundError as error:
        raise ValueError('Run record is unavailable for this older candidate. Train a new candidate to capture it.') from error
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Run manifest is unreadable or incomplete.') from error
