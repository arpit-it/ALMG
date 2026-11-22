"""Source-bound weighted mixture plans; metadata only, never training admission."""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import uuid

if __package__:
    from . import decoder_stream_indexes as indexes
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_indexes as indexes
    from run_manifest import digest, file_digest


def _sources(values):
    if not isinstance(values, list) or not 2 <= len(values) <= 8:
        raise ValueError('Choose two to eight completed local indexes and integer weights.')
    result = []
    for value in values:
        if (not isinstance(value, dict) or set(value) != {'index_id', 'weight'}
                or type(value['weight']) is not int or not 1 <= value['weight'] <= 1000):
            raise ValueError('Each source needs an index_id and an integer weight from 1 to 1000.')
        if not isinstance(value['index_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['index_id']):
            raise ValueError('Invalid streamed source index ID.')
        result.append(dict(value))
    if len({value['index_id'] for value in result}) != len(result):
        raise ValueError('Choose distinct source indexes.')
    return sorted(result, key=lambda value: value['index_id'])


def review(root, confirmed, sources, split='train'):
    if confirmed is not True:
        raise ValueError('Confirm local source metadata inspection for the mixture plan.')
    if split not in ('train', 'validation', 'test'):
        raise ValueError('Choose one existing dataset split.')
    selected = _sources(sources)
    total_weight = sum(value['weight'] for value in selected)
    result = []
    seen = set()
    for value in selected:
        index = indexes.read(root, value['index_id'])
        if index['status'] != 'complete':
            raise ValueError('Complete every source index before mixture planning.')
        if index['source_sha256'] in seen:
            raise ValueError('The same original source cannot appear twice in a mixture plan.')
        seen.add(index['source_sha256'])
        counts = index['split_counts']
        if (not isinstance(counts, dict) or set(counts) != {'train', 'validation', 'test'}
                or any(type(count) is not int or count < 0 for count in counts.values())
                or counts[split] == 0):
            raise ValueError('Every source needs records in the selected split.')
        result.append({**value, 'index_revision': index['revision'],
                       'index_file_sha256': index['files']['records.sqlite3'],
                       'source_id': index['source_id'], 'source_name': index['source_name'],
                       'source_sha256': index['source_sha256'], 'source_bytes': index['source_bytes'],
                       'split_counts': counts, 'available_records': counts[split],
                       'target_record_share': {'numerator': value['weight'], 'denominator': total_weight}})
    record = {
        'format': 'almg-stream-mixture-review-v1', 'schema_version': 1,
        'split': split, 'sources': result, 'total_weight': total_weight,
        'source_record_count_sum': sum(value['available_records'] for value in result),
        'method': {'version': 1, 'weight_unit': 'relative_unique_record_draws',
                   'share_calculation': 'source_weight_divided_by_total_weight',
                   'source_occurrences_expanded': False, 'split_reassignment': False,
                   'sampling_executed': False, 'cross_source_deduplication_checked': False,
                   'cross_source_contamination_checked': False},
        'scope': 'Metadata-only planning. Shares are requested record proportions, not token proportions, achieved samples or an epoch schedule. Record counts are summed per source and may overlap across sources. No source text is copied. Independent cross-source quality, permission and contamination review and a separately implemented sampler are required before training.',
        'training_approved': False, 'release_approved': False,
        'implementation_sha256': file_digest(Path(__file__)),
    }
    record['revision'] = digest(record)
    return record


def _folder(root, identifier):
    indexes._folder(root, identifier)
    return Path(root) / 'decoder-stream-mixtures' / identifier


def save(root, confirmed, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm saving this exact private mixture plan; training is not approved.')
    if not isinstance(reviewed, dict):
        raise ValueError('Reopen the exact mixture review before saving.')
    try:
        sources = [{key: value[key] for key in ('index_id', 'weight')} for value in reviewed['sources']]
        current = review(root, True, sources, reviewed['split'])
    except (KeyError, TypeError) as error:
        raise ValueError('Invalid mixture review.') from error
    if current != reviewed:
        raise ValueError('Mixture sources or weights changed; reopen the review before saving.')
    record = {'format': 'almg-saved-stream-mixture-v1', 'schema_version': 1,
              'id': uuid.uuid4().hex, 'review': current}
    record['revision'] = digest(record)
    parent = Path(root) / 'decoder-stream-mixtures'
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.mixture-', dir=parent) as temporary:
        staged = Path(temporary) / record['id']
        staged.mkdir()
        (staged / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        # Revalidate bindings immediately before publication.
        if review(root, True, sources, reviewed['split']) != current:
            raise ValueError('Mixture sources changed during saving.')
        staged.rename(parent / record['id'])
    return record


def read(root, identifier):
    path = _folder(root, identifier) / 'manifest.json'
    try:
        if path.stat().st_size > 65536:
            raise ValueError('Mixture manifest exceeds its size limit.')
        record = json.loads(path.read_text(encoding='utf-8'))
        if (set(record) != {'format', 'schema_version', 'id', 'review', 'revision'}
                or record['format'] != 'almg-saved-stream-mixture-v1'
                or type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['id'] != identifier
                or record['revision'] != digest({key: value for key, value in record.items() if key != 'revision'})):
            raise ValueError('Mixture manifest integrity changed.')
        saved = record['review']
        sources = [{key: value[key] for key in ('index_id', 'weight')} for value in saved['sources']]
        current = review(root, True, sources, saved['split'])
        # Keep prior producer provenance readable while verifying the versioned semantics.
        current['implementation_sha256'] = saved['implementation_sha256']
        current['revision'] = digest({key: value for key, value in current.items() if key != 'revision'})
        if current != saved:
            raise ValueError('Mixture source bindings or calculated shares changed.')
        return record
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Mixture plan or its bound sources are unavailable.') from error
