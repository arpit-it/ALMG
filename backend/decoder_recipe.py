"""Bounded CPU decoder construction and validated local artifact persistence."""
import numpy as np

CONTRACT = {
    'id': 'decoder_from_scratch', 'version': 1, 'name': 'Decoder from scratch (initialization only)',
    'description': 'Construct a tiny decoder-only Transformer from newly initialized weights. Training is not enabled.',
    'dataset': {'format': 'Batches of integer token IDs', 'imports': 'Generated local tokens only'},
    'hardware': {'initialization': 'CPU with NumPy'},
    'parameters': [{'id': 'seed', 'type': 'integer', 'default': 7}],
    'metrics': {'initialization': ['parameter_count', 'causal_prefix_max_error']},
    'exports': ['No trained model export; initialization evidence only'],
    'resume': 'Initialization is deterministic for a configuration and seed.',
    'status': 'initialization_only', 'capabilities': ['initialize'],
}


class Decoder:
    def __init__(self, config):
        defaults = {'vocab_size': 16, 'context_length': 16, 'width': 8, 'seed': 7}
        limits = {'vocab_size': (4, 256), 'context_length': (2, 128), 'width': (4, 64), 'seed': (0, 2**32 - 1)}
        if not isinstance(config, dict) or set(config) - set(defaults):
            raise ValueError('Only decoder dimensions and seed are supported; pretrained weights are not accepted.')
        self.config = {**defaults, **config}
        for name, value in self.config.items():
            low, high = limits[name]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} must be an integer between {low} and {high}.')
        rng = np.random.default_rng(self.config['seed'])
        v, t, d = (self.config[key] for key in ('vocab_size', 'context_length', 'width'))
        shapes = {'token_embedding': (v, d), 'position_embedding': (t, d),
                  'query': (d, d), 'key': (d, d), 'value': (d, d), 'attention_output': (d, d),
                  'feed_forward_in': (d, d * 2), 'feed_forward_out': (d * 2, d), 'head': (d, v)}
        self.parameters = {name: rng.normal(0, .02, shape).astype(np.float32) for name, shape in shapes.items()}

    def artifact(self):
        """Serialize only bounded, finite parameters matching this architecture."""
        expected = Decoder(self.config)
        if set(self.parameters) != set(expected.parameters):
            raise ValueError('Decoder parameter names do not match the architecture.')
        weights = {}
        for name, reference in expected.parameters.items():
            values = np.asarray(self.parameters[name])
            if (values.shape != reference.shape or values.dtype.kind not in 'iuf'
                    or not np.isfinite(values).all() or np.any(np.abs(values) > np.finfo(np.float32).max)):
                raise ValueError('Decoder parameter shapes and finite numeric values are required.')
            weights[name] = values.astype(np.float32).tolist()
        return {'format': 'almg-decoder-v1', 'schema_version': 1,
                'config': dict(self.config), 'parameters': weights}

    def save(self, path):
        """Atomically write a local JSON artifact; no executable serialization."""
        import json
        from pathlib import Path
        from tempfile import NamedTemporaryFile
        path = Path(path)
        content = json.dumps(self.artifact(), allow_nan=False)
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                    prefix='.almg-decoder-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path):
        """Load a bounded local decoder artifact after validating every tensor."""
        import json
        from pathlib import Path
        try:
            with Path(path).open('rb') as stream:
                content = stream.read(4 * 1024 * 1024 + 1)
            if len(content) > 4 * 1024 * 1024:
                raise ValueError('Decoder artifact exceeds the 4 MiB limit.')
            data = json.loads(content)
            if (not isinstance(data, dict) or data.get('format') != 'almg-decoder-v1'
                    or type(data.get('schema_version')) is not int or data['schema_version'] != 1
                    or set(data) != {'format', 'schema_version', 'config', 'parameters'}):
                raise ValueError('Unsupported decoder artifact format.')
            model = cls(data['config'])
            if not isinstance(data['parameters'], dict) or set(data['parameters']) != set(model.parameters):
                raise ValueError('Decoder parameter names do not match the architecture.')
            parameters = {}
            for name, reference in model.parameters.items():
                value = np.asarray(data['parameters'][name])
                if (value.shape != reference.shape or value.dtype.kind not in 'iuf'
                        or not np.isfinite(value).all() or np.any(np.abs(value) > np.finfo(np.float32).max)):
                    raise ValueError('Decoder parameter shapes and finite numeric values are required.')
                parameters[name] = value.astype(np.float32)
            model.parameters = parameters
            return model
        except (OSError, KeyError, TypeError, UnicodeError) as error:
            raise ValueError('Decoder artifact is unreadable or incomplete.') from error

    def logits(self, tokens):
        tokens = np.asarray(tokens)
        if (tokens.ndim != 2 or tokens.dtype.kind not in 'iu' or not 1 <= tokens.shape[0] <= 16
                or not 1 <= tokens.shape[1] <= self.config['context_length']
                or np.any(tokens < 0) or np.any(tokens >= self.config['vocab_size'])):
            raise ValueError('Provide a bounded batch of valid integer token IDs.')
        p = self.parameters
        x = p['token_embedding'][tokens] + p['position_embedding'][:tokens.shape[1]]
        def norm(values):
            return (values - values.mean(axis=-1, keepdims=True)) / np.sqrt(values.var(axis=-1, keepdims=True) + 1e-5)
        hidden = norm(x)
        scores = (hidden @ p['query']) @ (hidden @ p['key']).swapaxes(-1, -2) / np.sqrt(self.config['width'])
        scores = np.where(np.triu(np.ones(scores.shape[-2:], dtype=bool), 1), -np.inf, scores)
        scores = np.exp(scores - scores.max(axis=-1, keepdims=True))
        attention = scores / scores.sum(axis=-1, keepdims=True)
        x = x + (attention @ (hidden @ p['value'])) @ p['attention_output']
        x = x + np.maximum(norm(x) @ p['feed_forward_in'], 0) @ p['feed_forward_out']
        return norm(x) @ p['head']


def verify(initialize):
    """Exercise the registered constructor using generated tokens and no files."""
    first = initialize('decoder_from_scratch', {'seed': 7})
    second = initialize('decoder_from_scratch', {'seed': 7})
    tokens = np.array([[0, 1, 2, 3]])
    scores = first.logits(tokens)
    changed = tokens.copy()
    changed[0, -1] = 4
    causal_error = float(np.max(np.abs(scores[:, :-1] - first.logits(changed)[:, :-1])))
    deterministic = all(np.array_equal(value, second.parameters[name]) for name, value in first.parameters.items())
    if not deterministic or causal_error > 1e-7 or not np.isfinite(scores).all():
        raise ValueError('Decoder initialization failed determinism, causality or finite-output verification.')
    return {'passed': True, 'recipe': 'decoder_from_scratch', 'recipe_version': 1,
            'scope': 'Initialization only; language-model training and export remain unavailable.',
            'weight_origin': 'newly_initialized', 'pretrained_weights_loaded': False,
            'device': 'CPU', 'config': first.config,
            'parameter_count': sum(value.size for value in first.parameters.values()),
            'logits_shape': list(scores.shape), 'deterministic': deterministic,
            'causal_prefix_max_error': causal_error}
