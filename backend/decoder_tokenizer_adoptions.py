"""Confirmed tokenizer selection creates an immutable dataset; never starts training."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from . import decoder_datasets as datasets, decoder_tokenizer_experiments as experiments
    from . import decoder_tokenizer_compatibility as compatibility
    from .decoder_model_tokenizer import ModelTokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_datasets as datasets
    import decoder_tokenizer_experiments as experiments
    import decoder_tokenizer_compatibility as compatibility
    from decoder_model_tokenizer import ModelTokenizer
    from run_manifest import digest, file_digest


def adopt(root, identifier, confirmed, reviewed, reviewed_dataset):
    if confirmed is not True:
        raise ValueError('Confirm tokenizer selection for a new dataset version; training needs separate approval.')
    record = experiments.read(root, identifier)
    if not isinstance(reviewed, dict) or reviewed != record:
        raise ValueError('The tokenizer review changed. Reopen it before selection.')
    parent = datasets.read(root, record['dataset_id'])
    if not isinstance(reviewed_dataset, dict) or reviewed_dataset != parent:
        raise ValueError('The dataset review changed. Reopen it before tokenizer selection.')
    # Oversized vocabularies cannot be represented by this registered decoder.
    size = record['vocabulary_size']
    if not 4 <= size <= 256:
        raise ValueError('Tokenizer selection requires 4 to 256 actual IDs, including special tokens.')
    report = compatibility.review(root, identifier, record, {'vocab_size':size})
    if not report['vocabulary_and_lossless_checks_passed']:
        raise ValueError('Tokenizer selection blocked: every saved split must encode losslessly without UNK replacement.')
    approval = {'version':1, 'scope':'dataset_tokenizer_selection_only', 'confirmed_at':datetime.now(timezone.utc).isoformat(),
                'parent_dataset_id':parent['id'], 'experiment_id':identifier,
                'parent_manifest_sha256':digest(parent), 'experiment_revision':record['revision'],
                'compatibility_revision':report['revision'], 'model_training_approved':False}
    selection = {'parent_dataset_id':parent['id'], 'experiment_id':identifier,
                 'parent_manifest_sha256':digest(parent), 'experiment_revision':record['revision'], 'approval_sha256':digest(approval)}
    experiment_folder = Path(root)/'decoder-tokenizer-experiments'/identifier
    tokenizer = ModelTokenizer(json.loads((experiment_folder/'tokenizer.json').read_text(encoding='utf-8')), selection)
    parent_folder = Path(root)/'decoder-datasets'/parent['id']
    documents = (parent_folder/'documents.jsonl').read_bytes()
    rows = [json.loads(line) for line in documents.decode('utf-8').splitlines()]
    tokenizer.validate_training_documents([row['text'] for row in rows if row['split']=='train'])
    for row in rows:
        if tokenizer.decode(tokenizer.encode(row['text'])) != tokenizer.codec.normalized(row['text'])[0]:
            raise ValueError('Model tokenizer selection requires lossless round trips.')
    encoded = json.dumps(tokenizer.artifact(), ensure_ascii=False).encode('utf-8')
    if len(encoded) > 128*1024:
        raise ValueError('Tokenizer configuration exceeds the model bundle limit.')
    child = deepcopy(parent)
    child.update(id=uuid.uuid4().hex, tokenizer={'format':tokenizer.artifact()['format'], 'sha256':tokenizer.fingerprint(),
                 'fit_source':'reviewed_experiment_training_documents_only', 'vocabulary_size':size}, tokenizer_selection=approval,
                 derivation={'version':1, 'operation':'reviewed_tokenizer_selection', **selection,
                             'parent_derivation':parent.get('derivation')})
    child['findings'] = [finding for finding in child['findings'] if finding['kind'] not in ('tokenizer_limits','out_of_training_vocabulary')]
    directory = Path(root)/'decoder-datasets'
    with TemporaryDirectory(prefix='.tokenizer-selection-', dir=directory) as temporary:
        # Validate through the production dataset reader before atomic publication.
        staged_root = Path(temporary)
        staged = staged_root/'decoder-datasets'/child['id'];staged.mkdir(parents=True)
        (staged/'documents.jsonl').write_bytes(documents)
        (staged/'tokenizer.json').write_bytes(encoded)
        child['files'] = {name:file_digest(staged/name) for name in ('documents.jsonl','tokenizer.json')}
        (staged/'manifest.json').write_text(json.dumps(child, ensure_ascii=False, indent=2), encoding='utf-8')
        datasets.read(staged_root, child['id'])
        if datasets.read(root, parent['id']) != parent or experiments.read(root, identifier) != record:
            raise ValueError('Dataset or experiment changed during tokenizer selection.')
        staged.rename(directory/child['id'])
    return child
