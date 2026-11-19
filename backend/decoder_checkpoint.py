"""Bounded decoder SGD checkpoint state bound to an exact training revision."""
from pathlib import Path
if __package__:
    from . import decoder_bundle
else:
    import decoder_bundle


def revision(config, tokenizer, training_text, total_steps=100, learning_rate=.05):
    if (type(total_steps) is not int or not 1 <= total_steps <= 1000
            or type(learning_rate) not in (int, float) or not 0 < learning_rate <= 1):
        raise ValueError('Checkpoint training settings are outside supported bounds.')
    return {'schema_version': 1, 'optimizer': 'sgd-v1', 'config': dict(config),
            'tokenizer_sha256': tokenizer.fingerprint(),
            'training_text_sha256': decoder_bundle.digest(training_text),
            'total_steps': total_steps, 'learning_rate': learning_rate}


def save(folder, model, tokenizer, expected, completed_steps):
    if (type(completed_steps) is not int or not 0 <= completed_steps < expected['total_steps']
            or model.config != expected['config'] or tokenizer.fingerprint() != expected['tokenizer_sha256']):
        raise ValueError('Checkpoint model, tokenizer or completed step count is invalid.')
    record = {'kind': 'decoder_sgd_checkpoint', 'schema_version': 1, 'revision': expected,
              'revision_sha256': decoder_bundle.digest(expected), 'completed_steps': completed_steps}
    return decoder_bundle.save(folder, model, tokenizer, record)


def load(folder, expected):
    model, tokenizer, manifest = decoder_bundle.load(folder)
    record = manifest['training']
    if (record.get('kind') != 'decoder_sgd_checkpoint' or type(record.get('schema_version')) is not int
            or record['schema_version'] != 1 or record.get('revision') != expected
            or record.get('revision_sha256') != decoder_bundle.digest(expected)
            or type(record.get('completed_steps')) is not int
            or not 0 <= record['completed_steps'] < expected['total_steps']
            or model.config != expected['config'] or tokenizer.fingerprint() != expected['tokenizer_sha256']):
        raise ValueError('Checkpoint does not match the approved training revision; start a fresh run.')
    lineage = {'format': 'almg-decoder-sgd-checkpoint-v1', 'completed_steps': record['completed_steps'],
               'revision_sha256': record['revision_sha256'],
               'manifest_sha256': decoder_bundle.file_digest(Path(folder) / 'manifest.json')}
    return model, tokenizer, lineage
