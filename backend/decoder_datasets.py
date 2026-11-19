"""Immutable local-text preparation for future decoder jobs; never starts training."""
import json
import hashlib
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from .decoder_tokenizer import Tokenizer, ByteTokenizer
    from .run_manifest import digest, file_digest
else:
    from decoder_tokenizer import Tokenizer, ByteTokenizer
    from run_manifest import digest, file_digest


def prepare(root, documents, confirmed, tokenizer_kind="words"):
    if not isinstance(tokenizer_kind, str) or tokenizer_kind not in ('words', 'utf8_bytes'):
        raise ValueError('Choose word or UTF-8 byte tokenization.')
    tokenizer_type = ByteTokenizer if tokenizer_kind == 'utf8_bytes' else Tokenizer
    if confirmed is not True:
        raise ValueError('Confirm local decoder dataset preparation first.')
    if not isinstance(documents, list) or not 3 <= len(documents) <= 16:
        raise ValueError('Select 3 to 16 local text documents.')
    sources, unique, findings = [], {}, []
    total_bytes = 0
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError('Each document requires a name and UTF-8 text.')
        name = document.get('name')
        if 'data' in document:
            if not isinstance(document['data'], str) or len(document['data']) > 90000 or 'text' in document:
                raise ValueError('Provide bounded original UTF-8 bytes for each document.')
            encoded = base64.b64decode(document['data'], validate=True)
            text = encoded.decode('utf-8')
        else:
            text = document.get('text')
            if not isinstance(text, str):
                raise ValueError('Each document requires UTF-8 text or original bytes.')
            encoded = text.encode('utf-8')
        if not isinstance(name, str) or not 1 <= len(name) <= 255:
            raise ValueError('Each document requires a short source name.')
        if not isinstance(text, str) or any(ord(ch) < 32 and ch not in '\r\n\t' for ch in text):
            raise ValueError('Only plain UTF-8 text documents are supported.')
        total_bytes += len(encoded)
        if len(encoded) > 65536 or total_bytes > 128000:
            raise ValueError('Each document must fit 64 KiB; the selection must fit 128000 bytes.')
        normalized = ' '.join(Tokenizer.words(text.removeprefix('\ufeff')))
        group = digest(normalized)
        source_hash = hashlib.sha256(encoded).hexdigest()
        sources.append({'name': name, 'source_sha256': source_hash, 'utf8_bytes': len(encoded),
                        'normalized_sha256': group, 'license': 'user_provided_not_reviewed'})
        unique.setdefault(group, []).append({'name': name, 'text': normalized, 'source_sha256': source_hash})
    if len(unique) < 3:
        raise ValueError('Select at least three distinct documents for separate train, validation and test groups.')
    groups = sorted(unique)
    records = []
    for index, group in enumerate(groups):
        part = 'test' if index == 0 else ('validation' if index == 1 else 'train')
        candidates = sorted(unique[group], key=lambda row: (row['name'], row['source_sha256']))
        record = {**candidates[0], 'group': group, 'split': part}
        records.append(record)
        for duplicate in candidates[1:]:
            findings.append({'kind': 'duplicate_document', 'source': duplicate['name'],
                             'source_sha256': duplicate['source_sha256'], 'kept_source': record['name'],
                             'kept_source_sha256': record['source_sha256'], 'group': group})
        for source in sources:
            if source['normalized_sha256'] == group:
                source['split'] = part
    tokenizer = None
    try:
        tokenizer = tokenizer_type.fit([row['text'] for row in records if row['split'] == 'train'])
        for row in records:
            try:
                tokenizer.encode(row['text'])
            except ValueError:
                findings.append({'kind': 'out_of_training_vocabulary', 'source': row['name'], 'split': row['split']})
    except ValueError as error:
        findings.append({'kind': 'tokenizer_limits', 'message': str(error)})
    directory = Path(root) / 'decoder-datasets'
    directory.mkdir(parents=True, exist_ok=True)
    dataset_id = uuid.uuid4().hex
    sources.sort(key=lambda source: (source['name'], source['source_sha256']))
    manifest = {'format': 'almg-decoder-text-dataset-v1', 'schema_version': 1, 'id': dataset_id,
                'status': 'prepared_for_review', 'preparation_version': 1,
                'input_documents': len(documents), 'unique_documents': len(records),
                'dataset_sha256': digest(records), 'sources': sources, 'findings': findings,
                'splits': {part: sum(row['split'] == part for row in records) for part in ('train', 'validation', 'test')},
                'tokenizer': None if tokenizer is None else {'format': tokenizer.artifact()['format'],
                    'sha256': tokenizer.fingerprint(), 'fit_source': 'training_documents_only',
                    'vocabulary_size': len(tokenizer.vocabulary)}}
    with TemporaryDirectory(prefix='.prepare-', dir=directory) as temporary:
        staged = Path(temporary) / 'dataset'
        staged.mkdir()
        (staged / 'documents.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
        if tokenizer is not None:
            (staged / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
        manifest['files'] = {path.name: file_digest(path) for path in staged.iterdir()}
        (staged / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        staged.rename(directory / dataset_id)
    return manifest


def read(root, dataset_id):
    import re
    if not isinstance(dataset_id, str) or not re.fullmatch('[a-f0-9]{32}', dataset_id):
        raise ValueError('Invalid decoder dataset ID.')
    folder = Path(root) / 'decoder-datasets' / dataset_id
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('format') != 'almg-decoder-text-dataset-v1'
                or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
                or manifest.get('id') != dataset_id or not isinstance(manifest.get('files'), dict)
                or set(manifest['files']) not in ({'documents.jsonl'}, {'documents.jsonl', 'tokenizer.json'})):
            raise ValueError('Unsupported decoder dataset manifest.')
        for name, expected in manifest['files'].items():
            if file_digest(folder / name) != expected:
                raise ValueError('Decoder dataset file hash mismatch.')
        records = [json.loads(line) for line in (folder / 'documents.jsonl').read_text(encoding='utf-8').splitlines()]
        if digest(records) != manifest['dataset_sha256']:
            raise ValueError('Decoder dataset content revision does not match.')
        if (len(records) != manifest['unique_documents']
                or len({row['group'] for row in records}) != len(records)
                or manifest['splits'] != {part: sum(row['split'] == part for row in records) for part in ('train', 'validation', 'test')}):
            raise ValueError('Decoder dataset partition metadata does not match its content.')
        if 'tokenizer.json' in manifest['files']:
            tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8')))
            fitted = type(tokenizer).fit([row['text'] for row in records if row['split'] == 'train'])
            if (tokenizer.artifact()['format'] != manifest['tokenizer']['format']
                    or tokenizer.fingerprint() != manifest['tokenizer']['sha256'] or tokenizer.fingerprint() != fitted.fingerprint()):
                raise ValueError('Decoder tokenizer does not match the training partition.')
        return manifest
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Decoder dataset is unavailable or incomplete.') from error


def list_datasets(root):
    directory = Path(root) / 'decoder-datasets'
    manifests = []
    if directory.exists():
        for folder in directory.iterdir():
            if not folder.name.startswith('.'):
                try:
                    manifests.append(read(root, folder.name))
                except ValueError:
                    continue
    return {'datasets': manifests[-20:]}
