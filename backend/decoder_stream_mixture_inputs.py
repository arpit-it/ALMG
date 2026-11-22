"""Receipt-bound fixed-byte causal input inspection; never training admission."""
import json
from functools import wraps
from pathlib import Path
import platform
import sqlite3
import unicodedata

if __package__:
    from . import decoder_stream_mixture_sessions as sessions, decoder_stream_tokenizers as tokenizers
    from .decoder_tokenizer import ByteTokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixture_sessions as sessions
    import decoder_stream_tokenizers as tokenizers
    from decoder_tokenizer import ByteTokenizer
    from run_manifest import digest, file_digest

WIDTH = 16


def _source_errors(action):
    @wraps(action)
    def checked(*args, **kwargs):
        try:
            return action(*args, **kwargs)
        except (OSError, sqlite3.Error) as error:
            raise ValueError('Receipt input sources or tokenizer are unavailable; no valid inputs were produced.') from error
    return checked


def _load(root, session_id, sequence, tokenizer_id):
    state = sessions.read(root, session_id)
    view = sessions._bindings(root, state)
    directory = tokenizers._folder(root, tokenizer_id)
    paths = sessions.sampling._paths(root, view) + [directory / 'manifest.json', directory / 'tokenizer.json']
    before = sessions.sampling.overlap._signatures(paths)
    packet = sessions.batch(root, session_id, True, sequence)
    manifest = tokenizers.read(root, tokenizer_id)
    source = next((source for source in view['sources'] if source['index_id'] == manifest['index_id']), None)
    if (source is None or manifest['index_revision'] != source['index_revision']
            or manifest['source_provenance']['source_sha256'] != source['source_sha256']):
        raise ValueError('Choose a saved fixed-byte tokenizer bound to a current source in this mixture.')
    artifact = json.loads((directory / 'tokenizer.json').read_text(encoding='utf-8'))
    codec = ByteTokenizer.restore(artifact)
    if codec.fingerprint() != manifest['tokenizer_sha256']:
        raise ValueError('Tokenizer artifact changed during model-input inspection.')
    encoded = []
    for record in packet['records']:
        ids = codec.encode(record['text'])  # Existing 4096-byte per-document limit; never truncate.
        if bytes(ids).decode('utf-8') != record['text']:
            raise ValueError('Fixed-byte encoding changed a normalized source record.')
        encoded.append(ids)
    sessions._bindings(root, state)
    if sessions.sampling.overlap._signatures(paths) != before:
        raise ValueError('Model-input sources, declarations or tokenizer files changed.')
    reviewed = {
        'format': 'almg-stream-mixture-input-review-v1', 'schema_version': 1,
        'session_id': session_id, 'sequence': sequence, 'receipt': packet['receipt'], 'tokenizer': manifest,
        'tokenizer_sha256': codec.fingerprint(), 'vocabulary_size': 256, 'sequence_width': WIDTH,
        'document_token_counts': [len(ids) for ids in encoded],
        'total_target_tokens': sum(len(ids) - 1 for ids in encoded),
        'total_windows': sum((len(ids) - 1 + WIDTH - 1) // WIDTH for ids in encoded),
        'records_without_targets': [record['position'] for record, ids in zip(packet['records'], encoded) if len(ids) == 1],
        'method': {'version': 1, 'window_tokens': WIDTH + 1, 'stride': WIDTH,
                   'respect_document_boundaries': True, 'padding_value': 0, 'padding_is_special_token': False,
                   'loss_mask_required': True, 'unknown_replacement': False,
                   'record_order': 'committed_sampler_order_then_document_token_offset',
                   'weight_unit': 'source_records_not_tokens', 'joint_mixture_tokenizer_fit_performed': False,
                   'codec_fit_scope': 'selected_source_training_records_only_fixed_universal_byte_alphabet'},
        'runtime': {'python': platform.python_version(), 'unicode': unicodedata.unidata_version},
        'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
            ('decoder_stream_mixture_inputs.py', 'decoder_stream_mixture_sessions.py',
             'decoder_stream_mixture_sampling.py', 'decoder_stream_tokenizers.py', 'decoder_tokenizer.py')}),
        **{flag: False for flag in sessions.FLAGS},
        'scope': 'Read-only candidate model inputs from one immutable committed receipt. A shared saved fixed-byte codec retains its original single-source training provenance; no joint vocabulary fitting, special tokens, cross-document packing, quality clearance, sampler advancement or model training approval. Token IDs encode private source text. Short one-byte records have no causal targets and are reported explicitly; over-limit documents reject rather than truncate.',
    }
    reviewed['revision'] = digest(reviewed)
    return reviewed, packet, encoded


@_source_errors
def review(root, session_id, confirmed, sequence, reviewed_receipt, tokenizer_id, reviewed_tokenizer):
    if confirmed is not True:
        raise ValueError('Confirm private tokenized-input inspection; token IDs encode source text.')
    current, _, _ = _load(root, session_id, sequence, tokenizer_id)
    if current['receipt'] != reviewed_receipt or current['tokenizer'] != reviewed_tokenizer:
        raise ValueError('The committed receipt or tokenizer review changed. Reopen both artifacts.')
    return current


@_source_errors
def batch(root, session_id, confirmed, reviewed, cursor=None, batch_size=4):
    if confirmed is not True:
        raise ValueError('Confirm reviewing private model-input token IDs; training is not approved.')
    if type(batch_size) is not int or not 1 <= batch_size <= 16:
        raise ValueError('Choose one to 16 causal windows per batch.')
    if not isinstance(reviewed, dict) or reviewed.get('session_id') != session_id:
        raise ValueError('Reopen this session receipt input review.')
    current, packet, encoded = _load(root, session_id, reviewed.get('sequence'), reviewed.get('tokenizer', {}).get('id'))
    if current != reviewed:
        raise ValueError('Receipt input sources, declarations, tokenizer or implementation changed.')
    index, offset = 0, 0
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != {'revision', 'record_index', 'token_offset'}
                or cursor.get('revision') != current['revision'] or type(cursor.get('record_index')) is not int
                or not 0 <= cursor['record_index'] < len(encoded) or type(cursor.get('token_offset')) is not int
                or cursor['token_offset'] < 0 or cursor['token_offset'] % WIDTH
                or cursor['token_offset'] >= len(encoded[cursor['record_index']]) - 1):
            raise ValueError('Receipt model-input cursor is invalid or stale.')
        index, offset = cursor['record_index'], cursor['token_offset']
    inputs, targets, masks, lengths, provenance = [], [], [], [], []
    while index < len(encoded):
        ids = encoded[index]
        if offset >= len(ids) - 1:
            index += 1;offset = 0
            continue
        if len(inputs) == batch_size: break
        window = ids[offset:offset + WIDTH + 1]
        length = len(window) - 1
        inputs.append(window[:-1] + [0] * (WIDTH - length))
        targets.append(window[1:] + [0] * (WIDTH - length))
        masks.append([1] * length + [0] * (WIDTH - length));lengths.append(length)
        record = packet['records'][index]
        provenance.append({**{key: value for key, value in record.items() if key != 'text'},
                           'receipt_record_index': index, 'token_offset': offset, 'document_tokens': len(ids)})
        offset += WIDTH
    following = ({'revision': current['revision'], 'record_index': index, 'token_offset': offset}
                 if index < len(encoded) else None)
    final, _, _ = _load(root, session_id, current['sequence'], current['tokenizer']['id'])
    if final != current:
        raise ValueError('Model-input bindings changed during batching; discard this page.')
    return {'format': 'almg-stream-mixture-input-batch-v1', 'schema_version': 1,
            'session_id': session_id, 'sequence': current['sequence'], 'review_revision': current['revision'],
            'receipt_revision': current['receipt']['revision'], 'tokenizer_sha256': current['tokenizer_sha256'],
            'sequence_width': WIDTH, 'rows': len(inputs), 'inputs': inputs, 'targets': targets, 'loss_mask': masks,
            'sequence_lengths': lengths, 'provenance': provenance, 'real_target_tokens': sum(lengths),
            'receipt_target_tokens': current['total_target_tokens'], 'next_cursor': following,
            **{flag: False for flag in sessions.FLAGS}}
