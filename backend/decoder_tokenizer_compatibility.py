"""Read-only, source-bound tokenizer admission review for the bounded decoder."""
import json
from pathlib import Path

if __package__:
    from . import decoder_datasets as datasets, decoder_tokenizer_experiments as experiments
    from .decoder_special_tokens import SpecialTokenizer, restore_base
    from .run_manifest import digest, file_digest
else:
    import decoder_datasets as datasets
    import decoder_tokenizer_experiments as experiments
    from decoder_special_tokens import SpecialTokenizer, restore_base
    from run_manifest import digest, file_digest


def review(root, identifier, reviewed, config):
    """Re-encode every bounded input; never trust cached comparison summaries."""
    if (not isinstance(config, dict) or set(config) != {'vocab_size'}
            or type(config['vocab_size']) is not int or not 4 <= config['vocab_size'] <= 256):
        raise ValueError('Choose a decoder vocabulary size between 4 and 256.')
    record = experiments.read(root, identifier)
    if not isinstance(reviewed, dict) or reviewed != record:
        raise ValueError('The tokenizer review changed. Reopen the saved experiment.')
    dataset = datasets.read(root, record['dataset_id'])
    if (digest(dataset) != record['dataset_manifest_sha256']
            or dataset['dataset_sha256'] != record['dataset_sha256']):
        raise ValueError('The fitted dataset revision changed. Fit a new reviewed experiment.')
    folder = Path(root) / 'decoder-tokenizer-experiments' / identifier
    artifact = json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8'))
    model = (SpecialTokenizer.restore(artifact) if artifact.get('format') == 'almg-special-tokenizer-v1'
             else restore_base(artifact))
    rows = [json.loads(line) for line in
            (Path(root) / 'decoder-datasets' / dataset['id'] / 'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    training = [model.normalized(row['text'])[0] for row in rows if row['split'] == 'train']
    if digest(training) != model.training_sha256:
        raise ValueError('Tokenizer training provenance does not match the saved training split.')
    blockers = []
    actual = len(model.pieces)
    if not 4 <= actual <= 256:
        blockers.append({'code': 'recipe_vocabulary_limit', 'message': f'The tokenizer has {actual} IDs; this decoder supports 4 to 256.'})
    if actual != config['vocab_size']:
        blockers.append({'code': 'vocabulary_mismatch', 'message': f"Model vocabulary {config['vocab_size']} does not match all {actual} tokenizer IDs, including special IDs."})
    splits = {}
    for split in ('train', 'validation', 'test'):
        selected = [row for row in rows if row['split'] == split]
        missing = lossless = encoding_failures = invalid_ids = 0
        for row in selected:
            text, _ = model.normalized(row['text'])
            uncovered = model.uncovered(text) if hasattr(model, 'uncovered') else 0
            missing += uncovered
            try:
                tokens = model.encode(text)
                valid = bool(tokens) and all(type(token) is int and 0 <= token < actual for token in tokens)
                if not valid:
                    invalid_ids += 1
                elif model.decode(tokens) == text and not uncovered:
                    lossless += 1
            except (ValueError, UnicodeError):
                encoding_failures += 1
        splits[split] = {'documents': len(selected), 'lossless_documents': lossless,
                         'uncovered_characters': missing, 'encoding_failures': encoding_failures,
                         'invalid_id_documents': invalid_ids, 'lossless': bool(selected) and lossless == len(selected)}
        if not splits[split]['lossless']:
            blockers.append({'code': 'lossless_encoding_required', 'split': split,
                             'message': f'{split}: {lossless}/{len(selected)} records encode losslessly. UNK replacement cannot satisfy this gate.'})
    if experiments.read(root, identifier) != record or datasets.read(root, dataset['id']) != dataset:
        raise ValueError('Tokenizer or dataset changed during compatibility review.')
    result = {
        'format': 'almg-tokenizer-compatibility-review-v1', 'schema_version': 1,
        'experiment_id': identifier, 'experiment_revision': record['revision'],
        'tokenizer_sha256': record['tokenizer_sha256'], 'dataset_id': dataset['id'],
        'dataset_manifest_sha256': digest(dataset), 'dataset_sha256': dataset['dataset_sha256'],
        'recipe': {'id': 'decoder_from_scratch', 'version': 1, 'vocabulary_min': 4, 'vocabulary_max': 256},
        'model_config': dict(config), 'actual_vocabulary_size': actual,
        'special_tokens': record.get('special_tokens', {}), 'splits': splits,
        'vocabulary_and_lossless_checks_passed': not blockers, 'compatibility_blockers': blockers,
        'pretraining_allowed': False, 'model_training_enabled': False, 'release_approved': False,
        'remaining_gate': 'A separately reviewed immutable dataset/model tokenizer integration and explicit training approval are still required.',
        'scope': 'vocabulary_dimensions_id_bounds_and_all_split_lossless_encoding_only',
        'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
            ('decoder_tokenizer_compatibility.py', 'decoder_tokenizer_experiments.py', 'decoder_recipe.py',
             'decoder_bpe.py', 'decoder_character_bpe.py', 'decoder_unigram.py', 'decoder_special_tokens.py', 'decoder_datasets.py')}),
    }
    result['revision'] = digest(result)
    return result
