"""Transactional exhaustive cross-source lexical overlap diagnostics, never admission."""
from contextlib import closing, contextmanager
from itertools import combinations
import json
from pathlib import Path
import platform
import re
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unicodedata
import uuid

if __package__:
    from . import decoder_stream_mixtures as mixtures, decoder_stream_indexes as indexes
    from . import decoder_stream_mixture_overlap as exact
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixtures as mixtures
    import decoder_stream_indexes as indexes
    import decoder_stream_mixture_overlap as exact
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest

MAX_BATCH_PAIRS = 100
MAX_BATCH_CHARACTERS = 1024 * 1024
_LOCK = threading.RLock()
FORMAT = 'almg-stream-mixture-near-overlap-v1'


def _folder(root, audit_id):
    indexes._folder(root, audit_id)
    return Path(root) / 'decoder-stream-mixture-near-overlap' / audit_id


def _runtime():
    return {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
            'unicode': unicodedata.unidata_version}


def _implementation():
    return digest({'runtime': _runtime(), 'files': {name: file_digest(Path(__file__).with_name(name)) for name in
                   ('decoder_stream_mixture_near_overlap.py', 'decoder_stream_mixtures.py',
                    'decoder_stream_indexes.py', 'decoder_stream_mixture_overlap.py', 'decoder_tokenizer.py', 'run_manifest.py')}})


def _signatures(root, record):
    paths = [mixtures._folder(root, record['mixture_id']) / 'manifest.json']
    for source in record['sources']:
        directory = indexes._folder(root, source['index_id'])
        paths.extend([directory / 'manifest.json', directory / 'records.sqlite3'])
    return [list(value) for value in exact._signatures(paths)]


def _bindings(root, record):
    plan = mixtures.read(root, record['mixture_id'])
    if plan['revision'] != record['mixture_revision'] or plan['review']['sources'] != record['sources']:
        raise ValueError('Mixture source bindings changed; existing audit progress is preserved.')


def _state(db):
    row = db.execute('SELECT value FROM state WHERE id=1').fetchone()
    if row is None or len(row[0]) > 128000:
        raise ValueError('Near-overlap state is unavailable or oversized.')
    record = json.loads(row[0])
    if (not isinstance(record, dict) or record.get('format') != FORMAT
            or type(record.get('schema_version')) is not int or record['schema_version'] != 1
            or record.get('status') not in ('scanning', 'awaiting_publication')):
        raise ValueError('Unsupported mixture near-overlap state.')
    keys = ('source_pair_count', 'total_pairs', 'processed_pairs', 'exact_pairs_skipped',
            'short_pairs_skipped', 'compared_pairs', 'near_duplicate_pairs', 'cross_split_pairs', 'pair_index')
    if (any(record.get(key) is not False for key in ('training_approved', 'release_approved'))
            or any(type(record.get(key)) is not int or record[key] < 0 for key in keys)
            or record['processed_pairs'] > record['total_pairs']
            or record['processed_pairs'] != sum(record[key] for key in ('exact_pairs_skipped', 'short_pairs_skipped', 'compared_pairs'))
            or not record['cross_split_pairs'] <= record['near_duplicate_pairs'] <= record['compared_pairs']
            or record['pair_index'] > record['source_pair_count']
            or any(not isinstance(record.get(key), str) or (record[key] != '' and not re.fullmatch('[a-f0-9]{64}', record[key]))
                   for key in ('last_left', 'last_right'))
            or bool(record['last_left']) != bool(record['last_right'])):
        raise ValueError('Mixture near-overlap counters or cursor changed.')
    return record


def begin(root, mixture_id, confirmed, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm an exhaustive cross-source lexical overlap audit; cost is quadratic.')
    plan = mixtures.read(root, mixture_id)
    if not isinstance(reviewed, dict) or reviewed != plan:
        raise ValueError('Reopen the exact saved mixture before starting its near-overlap audit.')
    counts = [sum(source['split_counts'].values()) for source in plan['review']['sources']]
    pairs = list(combinations(range(len(counts)), 2))
    record = {
        'format': FORMAT, 'schema_version': 1, 'id': uuid.uuid4().hex, 'status': 'scanning',
        'mixture_id': mixture_id, 'mixture_revision': plan['revision'], 'sources': plan['review']['sources'],
        'source_pair_count': len(pairs), 'total_pairs': sum(counts[a] * counts[b] for a, b in pairs),
        'processed_pairs': 0, 'exact_pairs_skipped': 0, 'short_pairs_skipped': 0, 'compared_pairs': 0,
        'near_duplicate_pairs': 0, 'cross_split_pairs': 0, 'pair_index': 0, 'last_left': '', 'last_right': '',
        'implementation_sha256': _implementation(), 'runtime': _runtime(),
        'method': {'version': 1, 'name': 'word_shingle_jaccard', 'shingle_words': 5,
                   'minimum_words': 12, 'threshold': .8, 'all_saved_splits': True,
                   'source_weights_applied': False, 'source_occurrences_expanded': False,
                   'exact_identity_pairs': 'counted_separately_not_near_duplicate_findings', 'raw_text_included': False,
                   'cross_split_counter_scope': 'near_duplicate_findings_only_use_exact_audit_for_exact_matches',
                   'limitations': 'Exhaustive cross-source Cartesian comparisons; quadratic cost. Short records are not assessed. Lexical heuristic only, not semantic contamination clearance.'},
        'policy': 'diagnostic_only_no_training_admission_change', 'training_approved': False, 'release_approved': False,
    }
    record['source_signatures'] = _signatures(root, record)
    _bindings(root, record)
    if _signatures(root, record) != record['source_signatures']:
        raise ValueError('Mixture sources changed before audit preparation.')
    parent = _folder(root, record['id']).parent
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.near-', dir=parent) as temporary:
        staged = Path(temporary) / record['id']
        staged.mkdir()
        with indexes._connect(staged / 'audit.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
            db.execute('CREATE TABLE findings(pair_index INTEGER,left_group TEXT,right_group TEXT,value TEXT NOT NULL,PRIMARY KEY(pair_index,left_group,right_group))')
            db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(record, allow_nan=False),))
        _bindings(root, record)
        if _signatures(root, record) != record['source_signatures']:
            raise ValueError('Mixture sources changed during audit preparation.')
        staged.rename(parent / record['id'])
    return record


def read(root, audit_id):
    directory = _folder(root, audit_id)
    try:
        with indexes._connect(directory / 'audit.sqlite3', True) as db:
            record = _state(db)
        if record.get('id') != audit_id or any(record.get(key) is not False for key in ('training_approved', 'release_approved')):
            raise ValueError('Near-overlap audit identity or approval scope changed.')
        _bindings(root, record)
        path = directory / 'manifest.json'
        if path.exists():
            if path.stat().st_size > 128000:
                raise ValueError('Near-overlap manifest exceeds its size limit.')
            manifest = json.loads(path.read_text(encoding='utf-8'))
            expected = {**record, 'status': 'complete', 'files': {'audit.sqlite3': file_digest(directory / 'audit.sqlite3')}}
            expected['revision'] = digest(expected)
            if record['status'] != 'awaiting_publication' or manifest != expected:
                raise ValueError('Near-overlap manifest or finding database integrity changed.')
            return manifest
        return record
    except (OSError, sqlite3.Error, TypeError, KeyError, AttributeError) as error:
        raise ValueError('Mixture near-overlap audit is unavailable or incomplete.') from error


@contextmanager
def _source(root, record):
    with closing(sqlite3.connect(':memory:', uri=True, timeout=10)) as db:
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA query_only=ON')
        for position, source in enumerate(record['sources']):
            path = indexes._folder(root, source['index_id']) / 'records.sqlite3'
            db.execute(f'ATTACH DATABASE ? AS source{position}', (path.as_uri() + '?mode=ro',))
            db.execute(f'PRAGMA source{position}.cache_size=-2048')
        yield db


def _next(source, record):
    pairs = list(combinations(range(len(record['sources'])), 2))
    fields = ('group_sha256', 'text', 'split', 'first_line', 'first_byte_offset', 'raw_line_sha256', 'occurrences')
    columns = ','.join(f'{alias}.{field}' for alias in ('a', 'b') for field in fields)
    while record['pair_index'] < len(pairs):
        left, right = pairs[record['pair_index']]
        row = source.execute(
            f'SELECT {columns} FROM source{left}.documents a CROSS JOIN source{right}.documents b '
            'WHERE a.group_sha256>=? AND (a.group_sha256>? OR b.group_sha256>?) '
            'ORDER BY a.group_sha256,b.group_sha256 LIMIT 1',
            (record['last_left'], record['last_left'], record['last_right'])).fetchone()
        if row is not None:
            return row
        record['pair_index'] += 1
        record['last_left'] = record['last_right'] = ''
    return None


def _reference(item, source):
    group, _, split, line, offset, raw, occurrences = item
    return {'index_id': source['index_id'], 'source_id': source['source_id'], 'source_sha256': source['source_sha256'],
            'group': group, 'split': split, 'first_line': line, 'first_byte_offset': offset,
            'raw_line_sha256': raw, 'occurrences': occurrences}


def _compare(db, record, row):
    left, right = row[:7], row[7:]
    if any(item[2] not in ('train', 'validation', 'test') for item in (left, right)):
        raise ValueError('A source record has an unsupported saved split.')
    if left[0] == right[0]:
        record['exact_pairs_skipped'] += 1
    else:
        words = [Tokenizer.words(item[1]) for item in (left, right)]
        if min(map(len, words)) < 12:
            record['short_pairs_skipped'] += 1
        else:
            record['compared_pairs'] += 1
            a, b = [{tuple(value[i:i + 5]) for i in range(len(value) - 4)} for value in words]
            similarity = len(a & b) / len(a | b)
            if similarity >= .8:
                positions = list(combinations(range(len(record['sources'])), 2))[record['pair_index']]
                cross = left[2] != right[2]
                finding = {'pair_index': record['pair_index'], 'left_group': left[0], 'right_group': right[0],
                           'records': [_reference(item, record['sources'][position]) for item, position in zip((left, right), positions)],
                           'similarity': round(similarity, 6), 'cross_split': cross, 'text_omitted': True,
                           'kind': 'potential_evaluation_contamination' if cross else 'near_duplicate_records'}
                db.execute('INSERT INTO findings VALUES(?,?,?,?)',
                           (record['pair_index'], left[0], right[0], json.dumps(finding, ensure_ascii=False, allow_nan=False)))
                record['near_duplicate_pairs'] += 1
                record['cross_split_pairs'] += int(cross)
    record['processed_pairs'] += 1
    record['last_left'], record['last_right'] = left[0], right[0]


def _publish(root, record):
    _bindings(root, record)
    if _signatures(root, record) != record['source_signatures']:
        raise ValueError('Mixture source files changed before publication; progress is preserved.')
    directory = _folder(root, record['id'])
    manifest = {**record, 'status': 'complete', 'files': {'audit.sqlite3': file_digest(directory / 'audit.sqlite3')}}
    manifest['revision'] = digest(manifest)
    temporary = directory / (uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        temporary.replace(directory / 'manifest.json')
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def step(root, audit_id, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm the next bounded local near-overlap scan step.')
    with _LOCK:
        record = read(root, audit_id)
        if record['status'] == 'complete':
            return record
        if record['implementation_sha256'] != _implementation():
            raise ValueError('Near-overlap implementation/runtime changed. Preserve progress and start a new reviewed audit.')
        if _signatures(root, record) != record['source_signatures']:
            raise ValueError('Mixture source files changed; existing audit progress is preserved.')
        if record['status'] == 'awaiting_publication':
            return _publish(root, record)
        with indexes._connect(_folder(root, audit_id) / 'audit.sqlite3') as db, _source(root, record) as source:
            db.execute('BEGIN IMMEDIATE')
            record = _state(db)
            processed = characters = 0
            while processed < MAX_BATCH_PAIRS:
                row = _next(source, record)
                if row is None:
                    break
                size = len(row[1]) + len(row[8])
                if characters + size > MAX_BATCH_CHARACTERS:
                    if processed == 0:
                        raise ValueError('A record pair exceeds the bounded scan character budget.')
                    break
                _compare(db, record, row)
                processed += 1
                characters += size
            if _next(source, record) is None:
                if record['processed_pairs'] != record['total_pairs']:
                    raise ValueError('Cross-source pair totals differ from the saved mixture.')
                record['status'] = 'awaiting_publication'
            _bindings(root, record)
            if _signatures(root, record) != record['source_signatures']:
                raise ValueError('Mixture sources changed during scanning; this step was not committed.')
            db.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(record, allow_nan=False),))
        return _publish(root, record) if record['status'] == 'awaiting_publication' else record


def record_page(root, audit_id, confirmed, cursor=None, limit=10):
    if confirmed is not True:
        raise ValueError('Confirm local near-overlap finding review.')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Choose one to 20 near-overlap findings per page.')
    record = read(root, audit_id)
    if record['status'] != 'complete':
        raise ValueError('Complete the cross-source scan before reading findings.')
    paths = [_folder(root, audit_id) / name for name in ('audit.sqlite3', 'manifest.json')]
    signatures = (exact._signatures(paths), _signatures(root, record))
    if read(root, audit_id) != record or (exact._signatures(paths), _signatures(root, record)) != signatures:
        raise ValueError('Near-overlap finding sources changed before reading the page.')
    pair, left, right = -1, '', ''
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != {'revision', 'pair_index', 'left_group', 'right_group'}
                or cursor.get('revision') != record['revision'] or type(cursor.get('pair_index')) is not int
                or not 0 <= cursor['pair_index'] < record['source_pair_count']
                or any(not isinstance(cursor.get(key), str) or not re.fullmatch('[a-f0-9]{64}', cursor[key]) for key in ('left_group', 'right_group'))):
            raise ValueError('Near-overlap finding cursor is invalid or stale.')
        pair, left, right = cursor['pair_index'], cursor['left_group'], cursor['right_group']
    with indexes._connect(_folder(root, audit_id) / 'audit.sqlite3', True) as db:
        if cursor is not None and db.execute('SELECT 1 FROM findings WHERE pair_index=? AND left_group=? AND right_group=?', (pair, left, right)).fetchone() is None:
            raise ValueError('Near-overlap cursor does not identify a saved finding.')
        rows = db.execute('SELECT value FROM findings WHERE pair_index>? OR (pair_index=? AND '
                          '(left_group>? OR (left_group=? AND right_group>?))) ORDER BY pair_index,left_group,right_group LIMIT ?',
                          (pair, pair, left, left, right, limit + 1)).fetchall()
    values = [json.loads(row[0]) for row in rows[:limit]]
    if read(root, audit_id) != record or (exact._signatures(paths), _signatures(root, record)) != signatures:
        raise ValueError('Near-overlap finding sources changed while reading the page.')
    following = ({'revision': record['revision'], **{key: values[-1][key] for key in ('pair_index', 'left_group', 'right_group')}}
                 if len(rows) > limit else None)
    return {'format': 'almg-stream-mixture-near-overlap-page-v1', 'schema_version': 1,
            'audit_id': audit_id, 'audit_revision': record['revision'], 'records': values,
            'next_cursor': following, 'training_approved': False, 'release_approved': False}
