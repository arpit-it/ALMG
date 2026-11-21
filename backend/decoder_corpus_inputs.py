"""Reviewed, immutable text inputs for the planned-decoder optimizer.

This stage prepares inputs only. Saving it never approves or starts training.
"""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from . import decoder_dataset_training as datasets, decoder_architecture_feasibility as architecture
    from .run_manifest import digest, file_digest
else:
    import decoder_dataset_training as datasets, decoder_architecture_feasibility as architecture
    from run_manifest import digest, file_digest


def _inputs(records, tokenizer, manifest, length):
    splits = {part: [] for part in ('train', 'validation', 'test')}
    for row in records:
        tokens = tokenizer.encode(row['text'])
        for start in range(0, len(tokens) - 1, length):
            window = tokens[start:start + length + 1]
            count = len(window) - 1
            item = {'document_sha256': row['source_sha256'], 'group': row['group'], 'offset': start,
                    'inputs': window[:-1] + [0] * (length - count),
                    'targets': window[1:] + [0] * (length - count),
                    'target_mask': [1] * count + [0] * (length - count)}
            copies = manifest.get('mixing', {}).get('group_weights', {}).get(row['group'], 1) if row['split'] == 'train' else 1
            splits[row['split']].extend([item] * copies)
            if len(splits[row['split']]) > (64 if row['split'] == 'train' else 32):
                raise ValueError('Corpus inputs support at most 64 training and 32 windows per evaluation split.')
    return splits


def review(root, plan_id, initialized, dataset, length):
    if type(length) is not int or length not in (4, 8, 16):
        raise ValueError('Choose sequence length four, eight or sixteen.')
    _, source, _ = architecture._source(root, plan_id, initialized)
    if source['actual_parameter_count'] > 262144:
        raise ValueError('Corpus optimizer inputs support at most 262144 model parameters; training requires a supported reviewed recipe.')
    manifest, tokenizer, records, _ = datasets.preflight(root, dataset)
    declarations = manifest.get('license_declarations', {})
    pending = [item['source_sha256'] for item in manifest['sources']
               if declarations.get(item['source_sha256'], {}).get('basis') not in ('user_created', 'permission_recorded')]
    reasons = []
    if pending:
        reasons.append('Review source permissions in the local dataset before saving optimizer inputs.')
    if source['config']['vocab_size'] != len(tokenizer.vocabulary):
        reasons.append(f"Tokenizer has {len(tokenizer.vocabulary)} IDs; initialize a plan with that exact vocabulary size.")
    if length > source['config']['context_length']:
        reasons.append('Selected sequence length exceeds the initialized model context.')
    windows = _inputs(records, tokenizer, manifest, length)
    version=2 if length==16 else 1
    record = {'format': f'almg-decoder-corpus-input-review-v{version}', 'schema_version': version,
              'source': {'plan_id': plan_id, 'initialization_id': source['id'],
                         'initialization_revision': source['revision'], 'model_sha256': source['model_sha256']},
              'dataset_id': manifest['id'], 'dataset_revision': digest(manifest),
              'dataset_sha256': manifest['dataset_sha256'], 'tokenizer_sha256': tokenizer.fingerprint(),
              'vocab_size': len(tokenizer.vocabulary), 'sequence_length': length,
              'windows_sha256': digest(windows),
              'splits': {part: {'windows': len(rows), 'target_tokens': sum(sum(row['target_mask']) for row in rows)}
                         for part, rows in windows.items()},
              'pending_source_permissions': sorted(set(pending)), 'compatible': not reasons, 'blockers': reasons,
              'policy': 'document_boundaries_preserved_right_padding_masked_training_mixing_only',
              'training_approved': False, 'release_approved': False,
              'implementation_sha256': file_digest(Path(__file__))}
    record['revision'] = digest(record)
    return record


def save(root, plan_id, confirmed, initialized, dataset, length, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm saving private corpus inputs. This does not start training.')
    current = review(root, plan_id, initialized, dataset, length)
    if current != reviewed:
        raise ValueError('Corpus input review changed. Reopen it before saving.')
    if not current['compatible']:
        raise ValueError('Resolve corpus input blockers before saving.')
    manifest, tokenizer, records, _ = datasets.preflight(root, dataset)
    windows = _inputs(records, tokenizer, manifest, length)
    parent = Path(root) / 'decoder-corpus-inputs'
    parent.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    with TemporaryDirectory(prefix='.corpus-', dir=parent) as temporary:
        folder = Path(temporary) / identifier
        folder.mkdir()
        for name, value in (('dataset.json', manifest), ('tokenizer.json', tokenizer.artifact()), ('windows.json', windows)):
            (folder / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        record = {'format': f"almg-decoder-corpus-inputs-v{current['schema_version']}", 'schema_version': current['schema_version'], 'id': identifier,
                  'review': current, 'files': {name: file_digest(folder / name) for name in ('dataset.json', 'tokenizer.json', 'windows.json')}}
        record['revision'] = digest(record)
        (folder / 'record.json').write_text(json.dumps(record, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        _read(folder)
        folder.rename(parent / identifier)
    return record


def _read(folder):
    if (folder / 'record.json').stat().st_size > 128000:
        raise ValueError('Corpus input record exceeds its bounded size.')
    record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    if ((record.get('format'),record.get('schema_version')) not in (('almg-decoder-corpus-inputs-v1',1),('almg-decoder-corpus-inputs-v2',2))
            or record.get('id') != folder.name or record.get('revision') != digest({k: v for k, v in record.items() if k != 'revision'})
            or set(record.get('files', {})) != {'dataset.json', 'tokenizer.json', 'windows.json'}):
        raise ValueError('Invalid corpus input record.')
    for name, expected in record['files'].items():
        if (folder / name).stat().st_size > 2 * 1024 ** 2 or file_digest(folder / name) != expected:
            raise ValueError('Saved corpus input content changed.')
    approved = record['review']
    version=record['schema_version']
    if (approved.get('format'),approved.get('schema_version'))!=(f'almg-decoder-corpus-input-review-v{version}',version) or type(approved.get('sequence_length')) is not int or approved.get('sequence_length') not in ((16,) if version==2 else (4,8)):raise ValueError('Corpus input version/sequence binding changed.')
    if approved.get('revision') != digest({k: v for k, v in approved.items() if k != 'revision'}) or approved.get('compatible') is not True:
        raise ValueError('Invalid saved corpus input review.')
    manifest = json.loads((folder / 'dataset.json').read_text(encoding='utf-8'))
    tokenizer = datasets.Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8')))
    windows = json.loads((folder / 'windows.json').read_text(encoding='utf-8'))
    if digest(manifest) != approved['dataset_revision'] or tokenizer.fingerprint() != approved['tokenizer_sha256'] or digest(windows) != approved['windows_sha256']:
        raise ValueError('Saved corpus input review binding changed.')
    return record


def read(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('Select a saved corpus input ID.')
    return _read(Path(root) / 'decoder-corpus-inputs' / identifier)


def history(root, plan_id, initialized):
    architecture._source(root, plan_id, initialized)
    parent = Path(root) / 'decoder-corpus-inputs'
    records = [read(root, item.name) for item in sorted(parent.glob('[0-9a-f]' * 32)) if item.is_dir()]
    return [item for item in records if item['review']['source']['plan_id'] == plan_id
            and item['review']['source']['initialization_id'] == initialized['id']][-20:]
