"""Versioned local decoder bundles; no planner or release capability is enabled."""
from copy import deepcopy
from importlib.metadata import version
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory

if __package__:
    from .decoder_recipe import Decoder, PIPELINE, validate_pipeline
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    from decoder_recipe import Decoder, PIPELINE, validate_pipeline
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest


def save(destination, model, tokenizer, training, pretraining_stage='pretraining_fixture'):
    """Publish a new complete bundle directory without overwriting existing work."""
    if pretraining_stage not in ('pretraining_fixture', 'pretraining_local'):
        raise ValueError('Unsupported decoder pretraining stage.')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Decoder bundle destination already exists. Choose a new directory.')
    if model.config['vocab_size'] != len(tokenizer.vocabulary):
        raise ValueError('Decoder vocabulary size does not match its tokenizer.')
    if not isinstance(training, dict):
        raise ValueError('Decoder training record must be an object.')
    with TemporaryDirectory(prefix='.almg-decoder-bundle-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'bundle'
        staged.mkdir()
        model.save(staged / 'decoder.json')
        (staged / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
        manifest = {
            'format': 'almg-decoder-bundle-v1', 'schema_version': 1,
            'recipe': {'id': 'decoder_from_scratch', 'version': 1},
            'pipeline': deepcopy(PIPELINE), 'post_training': {'version':1, 'mode':'none'},
            'stages': {'architecture': 1, 'tokenization': 1, pretraining_stage: 1, 'artifact': 1},
            'config': dict(model.config), 'tokenizer_sha256': tokenizer.fingerprint(),
            'training': deepcopy(training), 'training_sha256': digest(training),
            'runtime': {'python': platform.python_version(), 'system': platform.system(),
                        'machine': platform.machine(), 'numpy': version('numpy')},
            'components': {name: file_digest(Path(__file__).with_name(name)) for name in
                           ('decoder_recipe.py', 'decoder_tokenizer.py', 'decoder_training.py', 'decoder_dataset_training.py', 'decoder_checkpoint.py', 'decoder_bundle.py')},
            'files': {name: file_digest(staged / name) for name in ('decoder.json', 'tokenizer.json')},
        }
        (staged / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        load(staged)
        if destination.exists():
            raise ValueError('Decoder bundle destination already exists. Choose a new directory.')
        staged.rename(destination)
    return manifest


def load(folder):
    """Check version and integrity before decoding bounded model/tokenizer files."""
    folder = Path(folder)
    try:
        with (folder / 'manifest.json').open('rb') as stream:
            data = stream.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError('Decoder bundle manifest is too large.')
        manifest = json.loads(data)
        if (not isinstance(manifest, dict) or manifest.get('format') != 'almg-decoder-bundle-v1'
                or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
                or digest(manifest.get('recipe')) != digest({'id': 'decoder_from_scratch', 'version': 1})
                or digest(manifest.get('stages')) not in (
                    digest({'architecture': 1, 'tokenization': 1, stage: 1, 'artifact': 1})
                    for stage in ('pretraining_fixture', 'pretraining_local'))
                or not isinstance(manifest.get('training'), dict)
                or not isinstance(manifest.get('files'), dict)
                or set(manifest['files']) != {'decoder.json', 'tokenizer.json'}):
            raise ValueError('Unsupported decoder bundle version or file set.')
        if 'pipeline' in manifest:
            validate_pipeline(manifest['pipeline'])
        if 'pipeline' in manifest or 'post_training' in manifest:
            if digest(manifest.get('post_training')) != digest({'version':1,'mode':'none'}):
                raise ValueError('Unsupported decoder post-training policy.')
        for name, expected in manifest['files'].items():
            if file_digest(folder / name) != expected:
                raise ValueError('Decoder bundle file hash mismatch: ' + name)
        if digest(manifest['training']) != manifest['training_sha256']:
            raise ValueError('Decoder bundle training record hash mismatch.')
        model = Decoder.load(folder / 'decoder.json')
        with (folder / 'tokenizer.json').open('rb') as stream:
            data = stream.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise ValueError('Decoder tokenizer artifact is too large.')
        tokenizer = Tokenizer.restore(json.loads(data))
        if (model.config != manifest['config'] or model.config['vocab_size'] != len(tokenizer.vocabulary)
                or tokenizer.fingerprint() != manifest['tokenizer_sha256']):
            raise ValueError('Decoder bundle model/tokenizer configuration mismatch.')
        return model, tokenizer, manifest
    except (OSError, KeyError, TypeError) as error:
        raise ValueError('Decoder bundle is unreadable or incomplete.') from error
