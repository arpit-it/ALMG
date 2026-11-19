"""User-declared source permissions in new immutable dataset versions."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from . import decoder_datasets as datasets
    from .run_manifest import digest
else:
    import decoder_datasets as datasets
    from run_manifest import digest


def declare(root, dataset_id, confirmed, reviewed, source_hash, basis, note):
    if confirmed is not True:
        raise ValueError('Confirm the selected source declaration and note.')
    parent = datasets.read(root, dataset_id)
    if not isinstance(reviewed, dict) or digest(reviewed) != digest(parent):
        raise ValueError('The dataset review changed. Reopen it before recording a declaration.')
    if not isinstance(source_hash, str) or source_hash not in {source['source_sha256'] for source in parent['sources']}:
        raise ValueError('Select a source hash from the reviewed dataset.')
    if not isinstance(basis, str) or basis not in datasets.LICENSE_BASES:
        raise ValueError('Choose a supported user-declared source basis.')
    if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1000:
        raise ValueError('Provide an evidence or source note of 1 to 1000 characters.')
    declaration = {'version':1,'basis':basis,'note':note.strip(),'user_declared':True}
    if parent.get('license_declarations', {}).get(source_hash) == declaration:
        raise ValueError('This source declaration is already recorded in the selected version.')
    manifest = json.loads(json.dumps(parent))
    manifest.update(id=uuid.uuid4().hex, status='prepared_for_review')
    manifest.setdefault('license_declarations', {})[source_hash] = declaration
    for source in manifest['sources']:
        if source['source_sha256'] == source_hash:
            source['license'] = datasets.LICENSE_BASES[basis]
    manifest['derivation'] = {'version':1,'operation':'record_source_permission',
                              'parent_dataset_id':dataset_id,'parent_manifest_sha256':digest(parent),
                              'source_sha256':source_hash,'previous_derivation':parent.get('derivation'),
                              'policy':'user_declaration_only_new_review_no_training_approval_transfer'}
    directory = Path(root)/'decoder-datasets'
    source_folder = directory/dataset_id
    with TemporaryDirectory(prefix='.permission-', dir=directory) as temporary:
        staged = Path(temporary)/'dataset'
        staged.mkdir()
        for name, expected in parent['files'].items():
            with (source_folder/name).open('rb') as source:
                data = source.read(256*1024+1)
            if len(data)>256*1024 or hashlib.sha256(data).hexdigest()!=expected:
                raise ValueError('Dataset content changed while recording the source declaration.')
            (staged/name).write_bytes(data)
        (staged/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        staged.rename(directory/manifest['id'])
    return manifest
