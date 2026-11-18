"""Offline tiny causal language-model LoRA validation; no user-model recipe."""
import platform
from tempfile import TemporaryDirectory
from pathlib import Path


def run():
    """Fit only rank-2 adapters, then verify frozen weights and adapter reload."""
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('The local LoRA fixture requires an Apple silicon Mac.')
    try:
        import mlx.core as mx
    except ImportError as error:
        raise ValueError('The local LoRA fixture requires MLX with Metal GPU access.') from error
    if not mx.metal.is_available():
        raise ValueError('Metal GPU access is unavailable for the local LoRA fixture.')
    # Explicit keys leave the application's inference random state untouched.
    with mx.stream(mx.gpu):
        # One causal self-attention block with frozen random base parameters.
        embedding = mx.random.normal((4, 8), key=mx.random.key(7))
        query = mx.random.normal((8, 8), key=mx.random.key(8)) * 0.1
        key = mx.random.normal((8, 8), key=mx.random.key(9)) * 0.1
        value = mx.random.normal((8, 8), key=mx.random.key(10)) * 0.1
        head = mx.random.normal((8, 4), key=mx.random.key(11)) * 0.1
        base = [embedding, query, key, value, head]
        before = [mx.array(weight) for weight in base]
        a = mx.random.normal((8, 2), key=mx.random.key(12)) * 0.1
        b = mx.zeros((2, 4))
        train = mx.array(token_sequences(8))
        held_out = mx.array(token_sequences(12))

        def logits(tokens, a, b):
            embedded = embedding[tokens]
            scores = (embedded @ query) @ mx.swapaxes(embedded @ key, -1, -2) / (8 ** 0.5)
            mask = mx.triu(mx.full((tokens.shape[1], tokens.shape[1]), -float('inf')), k=1)
            attention = mx.softmax(scores + mask, axis=-1)
            hidden = embedded + attention @ (embedded @ value)
            return hidden @ head + hidden @ a @ b

        def loss(a, b):
            scores = logits(train[:, :-1], a, b)
            correct = mx.take_along_axis(scores, train[:, 1:, None], axis=-1).squeeze(-1)
            return mx.mean(mx.logsumexp(scores, axis=-1) - correct)

        initial = float(loss(a, b).item())
        gradient = mx.grad(loss, argnums=(0, 1))
        for _ in range(100):
            da, db = gradient(a, b)
            a, b = a - 0.5 * da, b - 0.5 * db
            mx.eval(a, b)
        final = float(loss(a, b).item())
        frozen = all(bool(mx.array_equal(weight, original).item()) for weight, original in zip(base, before))
        scores = logits(held_out[:, :-1], a, b)
        accuracy = float(mx.mean(mx.argmax(scores, axis=-1) == held_out[:, 1:]).item())
        # Changing the last input token must not change earlier logits.
        altered = mx.concatenate([held_out[:, :-2], (held_out[:, -2:-1] + 1) % 4], axis=1)
        causal_error = float(mx.max(mx.abs(scores[:, :-1] - logits(altered, a, b)[:, :-1])).item())
        with TemporaryDirectory(prefix='almg-lora-fixture-') as folder:
            path = Path(folder) / 'adapter.npz'
            mx.savez(str(path), a=a, b=b)
            restored = mx.load(str(path))
            difference = float(mx.max(mx.abs(scores - logits(held_out[:, :-1], restored['a'], restored['b']))).item())
        generated = [0]
        for _ in range(11):
            generated.append(int(mx.argmax(logits(mx.array([generated]), a, b)[0, -1]).item()))
        generation_matches = generated == token_sequences(12)[0]
        passed = (final < initial * 0.1 and accuracy >= 0.95 and frozen
                  and difference < 1e-6 and causal_error < 1e-6 and generation_matches)
        if not passed:
            raise ValueError('Local LoRA fixture failed loss, next-token, frozen-weight, causality, generation or reload verification.')
    return {'passed': True, 'scope': 'Tiny causal language-model fixture; user-model fine-tuning is not enabled.',
            'device': 'Metal GPU', 'seed': 7, 'rank': 2, 'steps': 100,
            'initial_loss': initial, 'final_loss': final, 'held_out_next_token_accuracy': accuracy,
            'base_weights_unchanged': frozen, 'reload_max_error': difference,
            'causal_prefix_max_error': causal_error, 'trainable_parameters': 24,
            'frozen_parameters': 256, 'train_sequence_length': 8, 'test_sequence_length': 12,
            'generated_tokens': generated, 'generation_matches_fixture': generation_matches}


def token_sequences(length):
    """Generated four-token cycles; longer held-out contexts never appear in training."""
    return [[(offset + index) % 4 for index in range(length)] for offset in range(4)]
