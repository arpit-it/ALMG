"""Offline LoRA runtime smoke test; this is not a language-model recipe."""
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
        x = mx.random.normal((32, 4), key=mx.random.key(7))
        base = mx.random.normal((4, 4), key=mx.random.key(8)) * 0.1
        before = mx.array(base)
        a = mx.random.normal((4, 2), key=mx.random.key(9)) * 0.1
        b = mx.zeros((2, 4))
        target_a = mx.array([[1., 0.], [0., 1.], [0.5, 0.], [0., 0.5]])
        target_b = mx.array([[0.5, 0., -0.5, 0.], [0., 0.5, 0., -0.5]])
        y = x @ base + x @ target_a @ target_b

        def loss(a, b):
            return mx.mean(mx.square(x @ base + x @ a @ b - y))

        initial = float(loss(a, b).item())
        gradient = mx.grad(loss, argnums=(0, 1))
        for _ in range(100):
            da, db = gradient(a, b)
            a, b = a - 0.2 * da, b - 0.2 * db
            mx.eval(a, b)
        final = float(loss(a, b).item())
        frozen = bool(mx.array_equal(base, before).item())
        with TemporaryDirectory(prefix='almg-lora-fixture-') as folder:
            path = Path(folder) / 'adapter.npz'
            mx.savez(str(path), a=a, b=b)
            restored = mx.load(str(path))
            difference = float(mx.max(mx.abs(x @ a @ b - x @ restored['a'] @ restored['b'])).item())
        passed = final < initial * 0.1 and frozen and difference < 1e-6
        if not passed:
            raise ValueError('Local LoRA fixture failed loss, frozen-weight or reload verification.')
    return {'passed': True, 'scope': 'Tiny projection fixture; language-model fine-tuning is not enabled.',
            'device': 'Metal GPU', 'seed': 7, 'rank': 2, 'steps': 100,
            'initial_loss': initial, 'final_loss': final,
            'base_weights_unchanged': frozen, 'reload_max_error': difference}
