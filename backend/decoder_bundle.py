"""Versioned local decoder bundles; no planner or release capability is enabled."""
from copy import deepcopy
from importlib.metadata import version
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory

if __package__:
    from .decoder_recipe import Decoder, PIPELINE, validate_pipeline, architecture_version
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    from decoder_recipe import Decoder, PIPELINE, validate_pipeline, architecture_version
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest



def tokenization_version(tokenizer_format):
    return 3 if tokenizer_format == 'almg-reviewed-stream-model-tokenizer-v1' else 2 if tokenizer_format == 'almg-reviewed-model-tokenizer-v1' else 1


def pipeline_for(tokenizer_format, config=None):
    pipeline = deepcopy(PIPELINE)
    if config is not None and architecture_version(config) == 2:
        pipeline['stages']['architecture'] = {'version':2, 'interface':'almg-decoder-v1', 'status':'fresh_weights_vocabulary_up_to_512'}
    if tokenizer_format == 'almg-reviewed-model-tokenizer-v1':
        pipeline['stages']['tokenization'] = {'version':2, 'interface':'almg-reviewed-model-tokenizer-v1', 'status':'reviewed_bounded_local'}
    if tokenizer_format == 'almg-reviewed-stream-model-tokenizer-v1':
        pipeline['stages']['dataset_preparation'] = {'version':2, 'interface':'reviewed_source_bound_stream_windows_v1_to_v3', 'status':'persisted_input_scope_only'}
        pipeline['stages']['tokenization'] = {'version':3, 'interface':'almg-reviewed-stream-model-tokenizer-v1', 'status':'reviewed_stream_persistence_only'}
        pipeline['stages']['pretraining'] = {'version':1, 'interface':'reviewed_stream_training_requires_separate_approval', 'status':'initialization_only_no_optimizer_updates'}
        pipeline['stages']['evaluation'] = {'version':2, 'interface':'cpu_model_tokenizer_roundtrip', 'status':'initialization_persistence_only'}
    return pipeline


def save(destination, model, tokenizer, training, pretraining_stage='pretraining_fixture'):
    """Publish a new complete bundle directory without overwriting existing work."""
    if pretraining_stage not in ('pretraining_fixture', 'pretraining_local', 'initialization_check'):
        raise ValueError('Unsupported decoder pretraining stage.')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Decoder bundle destination already exists. Choose a new directory.')
    if model.config['vocab_size'] != len(tokenizer.vocabulary):
        raise ValueError('Decoder vocabulary size does not match its tokenizer.')
    if not isinstance(training, dict):
        raise ValueError('Decoder training record must be an object.')
    tokenization = tokenization_version(tokenizer.artifact()['format'])
    if (tokenization == 3) != (pretraining_stage == 'initialization_check'):
        raise ValueError('Streamed codec persistence requires its separate initialization-only stage; training is unavailable.')
    if tokenization == 3:
        tokenizer.validate_persistence_record(training)
    with TemporaryDirectory(prefix='.almg-decoder-bundle-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'bundle'
        staged.mkdir()
        model.save(staged / 'decoder.json')
        (staged / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
        manifest = {
            'format': 'almg-decoder-bundle-v1', 'schema_version': 1,
            'recipe': {'id': 'decoder_from_scratch', 'version': 1},
            'pipeline': pipeline_for(tokenizer.artifact()['format'], model.config), 'post_training': {'version':1, 'mode':'none'},
            'stages': {'architecture': architecture_version(model.config), 'tokenization': tokenization, pretraining_stage: 1, 'artifact': 1},
            'config': dict(model.config), 'tokenizer_sha256': tokenizer.fingerprint(),
            'training': deepcopy(training), 'training_sha256': digest(training),
            'runtime': {'python': platform.python_version(), 'system': platform.system(),
                        'machine': platform.machine(), 'numpy': version('numpy')},
            'components': {name: file_digest(Path(__file__).with_name(name)) for name in
                           ('decoder_recipe.py', 'decoder_tokenizer.py', 'decoder_training.py', 'decoder_dataset_training.py', 'decoder_checkpoint.py', 'decoder_bundle.py', 'decoder_model_tokenizer.py', 'decoder_tokenizer_adoptions.py', 'decoder_bpe.py', 'decoder_character_bpe.py', 'decoder_unigram.py', 'decoder_special_tokens.py', 'decoder_stream_model_tokenizer.py', 'decoder_stream_bpe.py', 'decoder_stream_iterative_bpe.py', 'decoder_stream_character_bpe.py', 'decoder_stream_unigram.py')},
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
                    digest({'architecture': architecture, 'tokenization': tokenization, stage: 1, 'artifact': 1})
                    for stage in ('pretraining_fixture', 'pretraining_local', 'initialization_check') for tokenization in (1,2,3) for architecture in (1,2)
                    if (tokenization == 3) == (stage == 'initialization_check'))
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
        if manifest['stages']['architecture'] != architecture_version(model.config):
            raise ValueError('Decoder bundle architecture version does not match its vocabulary profile.')
        expected_version = tokenization_version(tokenizer.artifact()['format'])
        if manifest['stages']['tokenization'] != expected_version:
            raise ValueError('Decoder bundle tokenization version does not match its artifact.')
        if expected_version in (2,3) and digest(manifest.get('pipeline')) != digest(pipeline_for(tokenizer.artifact()['format'], model.config)):
            raise ValueError('Reviewed model tokenizer pipeline contract does not match.')
        if expected_version == 3:
            tokenizer.validate_persistence_record(manifest['training'])
            if model.config != {'vocab_size':len(tokenizer.vocabulary), 'context_length':16, 'width':8, 'seed':7}:
                raise ValueError('Stream persistence requires the reviewed tiny initialization profile.')
            fresh = Decoder(model.config)
            if any(not (model.parameters[name] == fresh.parameters[name]).all() for name in fresh.parameters):
                raise ValueError('Initialization-only stream bundle contains modified parameters.')
        if (model.config != manifest['config'] or model.config['vocab_size'] != len(tokenizer.vocabulary)
                or tokenizer.fingerprint() != manifest['tokenizer_sha256']):
            raise ValueError('Decoder bundle model/tokenizer configuration mismatch.')
        return model, tokenizer, manifest
    except (OSError, KeyError, TypeError) as error:
        raise ValueError('Decoder bundle is unreadable or incomplete.') from error
