"""Optional offline pretraining verification for the registered tiny decoder."""
import platform


def run(initialize):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('The local decoder training check requires an Apple silicon Mac.')
    try:
        import mlx.core as mx
    except ImportError as error:
        raise ValueError('The local decoder training check requires MLX with Metal access.') from error
    if not mx.metal.is_available():
        raise ValueError('Metal GPU access is unavailable for the local decoder training check.')
    import numpy as np
    if __package__:
        from .decoder_tokenizer import Tokenizer
    else:
        from decoder_tokenizer import Tokenizer
    words = ['amber', 'birch', 'cedar', 'dune']
    training_text = [' '.join(words[(offset + index) % 4] for index in range(8)) for offset in range(4)]
    held_out_text = [' '.join(words[(offset + index) % 4] for index in range(12)) for offset in range(4)]
    tokenizer = Tokenizer.fit(training_text)
    model = initialize('decoder_from_scratch', {'vocab_size': len(tokenizer.vocabulary), 'seed': 7})
    with mx.stream(mx.gpu):
        parameters = {name: mx.array(value) for name, value in model.parameters.items()}
        original = {name: mx.array(value) for name, value in parameters.items()}
        train = mx.array([tokenizer.encode(text) for text in training_text])
        held_out = mx.array([tokenizer.encode(text) for text in held_out_text])

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
            scores = logits(p, train[:, :-1])
            correct = mx.take_along_axis(scores, train[:, 1:, None], axis=-1).squeeze(-1)
            return mx.mean(mx.logsumexp(scores, axis=-1) - correct)

        initial = float(loss(parameters).item())
        gradient = mx.grad(loss)
        for _ in range(100):
            gradients = gradient(parameters)
            parameters = {name: value - .05 * gradients[name] for name, value in parameters.items()}
            mx.eval(parameters)
        final = float(loss(parameters).item())
        scores = logits(parameters, held_out[:, :-1])
        accuracy = float(mx.mean(mx.argmax(scores, axis=-1) == held_out[:, 1:]).item())
        altered = mx.concatenate([held_out[:, :-2], (held_out[:, -2:-1] + 1) % 4], axis=1)
        causal_error = float(mx.max(mx.abs(scores[:, :-1] - logits(parameters, altered)[:, :-1])).item())
        changed = [name for name, value in parameters.items()
                   if not bool(mx.array_equal(value, original[name]).item())]
        finite = all(bool(mx.all(mx.isfinite(value)).item()) for value in parameters.values())
        generated = [0]
        for _ in range(11):
            generated.append(int(mx.argmax(logits(parameters, mx.array([generated]))[0, -1]).item()))
        matches = generated == [index % 4 for index in range(12)]
        model.parameters = {name: np.array(value) for name, value in parameters.items()}
        cpu_error = float(np.max(np.abs(model.logits(np.array(held_out)[:, :-1]) - np.array(scores))))
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='almg-decoder-roundtrip-') as folder:
            if __package__:
                from . import decoder_bundle
            else:
                import decoder_bundle
            training_record = {'seed': model.config['seed'], 'steps': 100, 'learning_rate': .05,
                               'weight_origin': 'newly_initialized', 'device': 'Metal GPU',
                               'mlx_version': decoder_bundle.version('mlx'),
                               'training_text_sha256': decoder_bundle.digest(training_text),
                               'held_out_text_sha256': decoder_bundle.digest(held_out_text),
                               'initial_loss': initial, 'final_loss': final,
                               'held_out_next_token_accuracy': accuracy}
            destination = Path(folder) / 'bundle'
            bundle_manifest = decoder_bundle.save(destination, model, tokenizer, training_record)
            restored, restored_tokenizer, restored_manifest = decoder_bundle.load(destination)
            token_roundtrip = (restored_tokenizer.encode(held_out_text[0]) == tokenizer.encode(held_out_text[0])
                               and restored_tokenizer.fingerprint() == tokenizer.fingerprint())
            generated_text = restored_tokenizer.decode(generated)
            reload_error = float(np.max(np.abs(model.logits(np.array(held_out)[:, :-1]) - restored.logits(np.array(held_out)[:, :-1]))))
            artifact_bytes = (destination / 'decoder.json').stat().st_size
            bundle_roundtrip = restored_manifest == bundle_manifest
        if not (finite and final < initial * .1 and accuracy >= .95 and causal_error < 1e-6
                and len(changed) == len(parameters) and matches and cpu_error < 1e-5 and reload_error < 1e-7 and token_roundtrip and bundle_roundtrip):
            raise ValueError('Decoder training failed loss, held-out, causality, full-parameter or generation verification.')
    return {'passed': True, 'scope': 'Generated local-text training fixture only; user-dataset pretraining and export remain unavailable.',
            'recipe': 'decoder_from_scratch', 'recipe_version': 1, 'stage': 'pretraining_fixture', 'stage_version': 1,
            'weight_origin': 'newly_initialized', 'pretrained_weights_loaded': False,
            'device': 'Metal GPU', 'config': model.config, 'steps': 100, 'learning_rate': .05,
            'trainable_parameters': sum(value.size for value in model.parameters.values()),
            'updated_parameter_groups': changed, 'frozen_parameters': 0,
            'initial_loss': initial, 'final_loss': final, 'held_out_next_token_accuracy': accuracy,
            'train_sequence_length': 8, 'held_out_sequence_length': 12,
            'causal_prefix_max_error': causal_error, 'generated_tokens': generated,
            'generation_matches_fixture': matches, 'cpu_inference_max_error': cpu_error,
            'artifact_format': 'almg-decoder-v1', 'artifact_bytes': artifact_bytes,
            'artifact_reload_max_error': reload_error, 'temporary_artifact_removed': True, 'generated_text': generated_text,
            'bundle': {'format': bundle_manifest['format'], 'stage_versions': bundle_manifest['stages'],
                       'verified_files': list(bundle_manifest['files']), 'artifact_roundtrip': bundle_roundtrip,
                       'training_record_sha256': bundle_manifest['training_sha256']},
            'tokenizer': {'format': tokenizer.artifact()['format'], 'stage_version': 1,
                          'vocabulary_size': len(tokenizer.vocabulary), 'sha256': tokenizer.fingerprint(),
                          'fit_source': 'training_documents_only', 'training_documents': len(training_text),
                          'held_out_documents': len(held_out_text), 'artifact_roundtrip': token_roundtrip}}
