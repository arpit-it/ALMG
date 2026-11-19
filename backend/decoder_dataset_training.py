"""Bounded experimental decoder trials over an explicitly reviewed local dataset."""
import json
from pathlib import Path
import platform

if __package__:
    from . import decoder_datasets, decoder_bundle, decoder_checkpoint, decoder_training
    from .decoder_tokenizer import Tokenizer
else:
    import decoder_datasets, decoder_bundle, decoder_checkpoint, decoder_training
    from decoder_tokenizer import Tokenizer


def preflight(root, reviewed):
    if not isinstance(reviewed, dict):
        raise ValueError('Review a prepared local decoder dataset first.')
    manifest = decoder_datasets.read(root, reviewed.get('id'))
    if decoder_bundle.digest(manifest) != decoder_bundle.digest(reviewed):
        raise ValueError('The dataset review changed. Reopen it and approve the current version.')
    if manifest['tokenizer'] is None or 'tokenizer.json' not in manifest['files'] or any(finding['kind'] in ('tokenizer_limits', 'out_of_training_vocabulary') for finding in manifest['findings']):
        raise ValueError('Resolve tokenizer or evaluation-vocabulary findings before training.')
    report = decoder_datasets.quality_report(root, manifest['id'])
    if report['cross_split_pairs']:
        raise ValueError(
            f"Evaluation contamination check blocked training: {report['cross_split_pairs']} "
            'near-duplicate document pairs cross saved splits. Analyze local text quality '
            'to review affected records, then prepare a dataset with independent evaluation documents.')
    folder = Path(root) / 'decoder-datasets' / manifest['id']
    tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8')))
    records = [json.loads(line) for line in (folder / 'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    batches = {part: [] for part in ('train', 'validation', 'test')}
    for row in records:
        tokens = tokenizer.encode(row['text'])
        if len(tokens) < 2:
            raise ValueError('Each training/evaluation document needs at least two tokens.')
        for start in range(0, len(tokens) - 1, 16):
            window = tokens[start:start + 17]
            copies = manifest.get('mixing', {}).get('group_weights', {}).get(row['group'], 1) if row['split'] == 'train' else 1
            batches[row['split']].extend([window] * copies)
            if len(batches[row['split']]) > (64 if row['split'] == 'train' else 32):
                raise ValueError('This small trial supports at most 64 training and 32 windows per evaluation split. Prepare a smaller dataset.')
    if not all(batches.values()) or len(batches['train']) > 64 or any(len(batches[part]) > 32 for part in ('validation', 'test')):
        raise ValueError('This small trial supports at most 64 training and 32 windows per evaluation split. Prepare a smaller dataset.')
    return manifest, tokenizer, records, batches


def run(initialize, root, dataset, work_directory, stop=None):
    def boundary():
        if stop is not None and stop():
            raise decoder_training.Cancelled('Cancelled at a training boundary. Saved checkpoints are retained; approve resume to continue.')
    boundary()
    manifest, tokenizer, records, batches = preflight(root, dataset)
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('This local decoder trial requires an Apple silicon Mac.')
    try:
        import mlx.core as mx
    except ImportError as error:
        raise ValueError('This local decoder trial requires MLX with Metal access.') from error
    if not mx.metal.is_available():
        raise ValueError('Metal access is unavailable for this local decoder trial.')
    import numpy as np
    model = initialize('decoder_from_scratch', {'vocab_size': len(tokenizer.vocabulary), 'seed': 7})
    workspace = Path(work_directory)
    workspace.mkdir(parents=True, exist_ok=True)
    train_text = [row['text'] for row in records if row['split'] == 'train']
    expected = decoder_checkpoint.revision(model.config, tokenizer, train_text)
    expected.update(training_mode='reviewed_local_text', dataset_revision=manifest['dataset_sha256'])
    if 'mixing' in manifest:
        expected['sampling_revision'] = decoder_bundle.digest(manifest['mixing'])
    checkpoint = workspace / 'step-50'
    reused = checkpoint.exists()
    with mx.stream(mx.gpu):
        parameters = {name: mx.array(value) for name, value in model.parameters.items()}
        initial_parameters = dict(parameters)
        if reused:
            restored, _, lineage = decoder_checkpoint.load(checkpoint, expected)
            parameters = {name: mx.array(value) for name, value in restored.parameters.items()}
        else:
            lineage = {'completed_steps': 0}
        train = [mx.array([window]) for window in batches['train']]

        def norm(values):
            return (values - mx.mean(values, axis=-1, keepdims=True)) / mx.sqrt(mx.var(values, axis=-1, keepdims=True) + 1e-5)

        def logits(p, tokens):
            x = p['token_embedding'][tokens] + p['position_embedding'][:tokens.shape[1]]
            hidden = norm(x)
            scores = (hidden @ p['query']) @ mx.swapaxes(hidden @ p['key'], -1, -2) / (model.config['width'] ** .5)
            mask = mx.triu(mx.full((tokens.shape[1], tokens.shape[1]), -float('inf')), k=1)
            attention = mx.softmax(scores + mask, axis=-1)
            x = x + (attention @ (hidden @ p['value'])) @ p['attention_output']
            x = x + mx.maximum(norm(x) @ p['feed_forward_in'], 0) @ p['feed_forward_out']
            return norm(x) @ p['head']

        def loss(p):
            total = mx.array(0.0)
            count = 0
            for window in train:
                scores = logits(p, window[:, :-1])
                correct = mx.take_along_axis(scores, window[:, 1:, None], axis=-1).squeeze(-1)
                total = total + mx.sum(mx.logsumexp(scores, axis=-1) - correct)
                count += window.shape[1] - 1
            return total / count

        initial_loss = float(loss(initial_parameters).item())
        gradient = mx.grad(loss)
        for step in range(lineage['completed_steps'], 100):
            boundary()
            gradients = gradient(parameters)
            parameters = {name: value - .05 * gradients[name] for name, value in parameters.items()}
            mx.eval(parameters)
            if step + 1 == 50 and not reused:
                model.parameters = {name: np.array(value) for name, value in parameters.items()}
                decoder_checkpoint.save(checkpoint, model, tokenizer, expected, 50, pretraining_stage='pretraining_local')
        final_loss = float(loss(parameters).item())
        model.parameters = {name: np.array(value) for name, value in parameters.items()}
        probe = batches['test'][0][:-1]
        cpu_error = float(np.max(np.abs(model.logits([probe]) - np.array(logits(parameters, mx.array([probe]))))))
        if cpu_error >= 1e-5:
            raise ValueError('CPU decoder inference does not match the training implementation.')
        if not np.isfinite(final_loss) or not all(np.isfinite(value).all() for value in model.parameters.values()):
            raise ValueError('Decoder training produced nonfinite values; no completed bundle was published.')

    def accuracy(part):
        correct = total = 0
        for window in batches[part]:
            predicted = np.argmax(model.logits([window[:-1]])[0], axis=-1)
            correct += int(np.sum(predicted == np.array(window[1:])))
            total += len(window) - 1
        return correct / total

    validation, test = accuracy('validation'), accuracy('test')
    metrics = {'initial_train_loss': initial_loss, 'final_train_loss': final_loss,
               'validation_next_token_accuracy': validation, 'held_out_next_token_accuracy': test,
               'target_next_token_accuracy': .8, 'passed': bool(min(validation, test) >= .8 and final_loss < initial_loss)}
    generated = [batches['train'][0][0]]
    for _ in range(11):
        generated.append(int(np.argmax(model.logits([generated])[0, -1])))
    record = {'scope': 'reviewed_local_text_trial', 'dataset_id': manifest['id'],
              'dataset_sha256': manifest['dataset_sha256'], 'review_sha256': decoder_bundle.digest(manifest),
              'seed': 7, 'steps': 100, 'learning_rate': .05, 'weight_origin': 'newly_initialized',
              'device': 'Metal GPU', 'mlx_version': decoder_bundle.version('mlx'), 'evaluation': metrics}
    if 'mixing' in manifest:
        record['sampling'] = {**manifest['mixing'], 'windows': {part: len(windows) for part, windows in batches.items()}}
    boundary()
    decoder_bundle.save(workspace / 'bundle', model, tokenizer, record, pretraining_stage='pretraining_local')
    decoder_bundle.load(workspace / 'bundle')
    return {'scope': 'Small reviewed-local-text trial; general model release is not enabled.',
            'recipe': 'decoder_from_scratch', 'dataset_id': manifest['id'], 'dataset_sha256': manifest['dataset_sha256'],
            'metrics': metrics, 'generated_text': tokenizer.decode(generated), 'trainable_parameters': sum(v.size for v in model.parameters.values()),
            'checkpoint': {'completed_steps': 50, 'reused_existing_checkpoint': reused},
            'bundle_format': 'almg-decoder-bundle-v1', 'stage': 'pretraining_local', 'stage_version': 1,
            'cpu_inference_max_error': cpu_error,
            **({'sampling':record['sampling']} if 'sampling' in record else {})}
