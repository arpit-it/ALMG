"""Durable one-pass weighted record sessions with idempotent, text-free receipts."""
from contextlib import ExitStack
import json
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import threading
import uuid

if __package__:
    from . import decoder_stream_mixture_sampling as sampling
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixture_sampling as sampling
    from run_manifest import digest, file_digest

_LOCK = threading.RLock()
MAX_BATCH = 16
MAX_JSON = 128000
FLAGS = ('permission_verified', 'quality_clearance', 'training_approved', 'release_approved')


def _folder(root, identifier):
    sampling.indexes._folder(root, identifier)
    return Path(root) / 'decoder-stream-mixture-sessions' / identifier


def _review(root, mixture_id):
    source = sampling._context(root, mixture_id)
    result = {'format': 'almg-stream-mixture-session-review-v1', 'schema_version': 1,
              'mixture_id': mixture_id, 'source_review': source, 'maximum_batch_records': MAX_BATCH,
              'source_pass_record_limit': None, 'preview_cap_applied': False,
              'implementation_sha256': digest({'session_reader': file_digest(Path(__file__)),
                                                'source_reader': source['implementation_sha256']}),
              'runtime': source['runtime'], **{flag: False for flag in FLAGS},
              'scope': 'Explicitly stepped one-pass record reader, not model training. Same deterministic weighted interleaving as preview; no replacement within each source, no cross-source deduplication or randomized epochs. Source weights affect ordering until exhaustion, not final source capacities. Receipts persist references and payload hashes, never normalized text. The 256-record preview cap does not apply. Quality, permission verification and training approval remain separate.'}
    result['revision'] = digest(result)
    return result


def review(root, mixture_id, confirmed, reviewed):
    sampling.review(root, mixture_id, confirmed, reviewed)
    return _review(root, mixture_id)


def _seal(value):
    value['revision'] = digest({key: item for key, item in value.items() if key != 'revision'})
    return value


def _json(raw):
    if not isinstance(raw, str) or len(raw) > MAX_JSON:
        raise ValueError('Sampler metadata is unavailable or oversized.')
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('revision') != digest({key: item for key, item in value.items() if key != 'revision'}):
        raise ValueError('Sampler metadata integrity changed.')
    return value


def _state(db):
    row = db.execute('SELECT value FROM state WHERE id=1').fetchone()
    if row is None: raise ValueError('Sampler state is unavailable.')
    state = _json(row[0])
    view = state['review']['source_review']
    sources = view['sources']
    if (state.get('format') != 'almg-stream-mixture-session-v1' or type(state.get('schema_version')) is not int
            or state['schema_version'] != 1 or state.get('status') not in ('active', 'awaiting_publication')
            or any(state.get(flag) is not False for flag in FLAGS)
            or state['review'].get('revision') != digest({key: item for key, item in state['review'].items() if key != 'revision'})
            or type(state.get('position')) is not int or not 0 <= state['position'] <= view['total_available_source_records']
            or type(state.get('sequence')) is not int or state['sequence'] < 0
            or any(not isinstance(state.get(key), list) or len(state[key]) != len(sources) for key in ('emitted', 'credits', 'last_groups'))
            or any(type(n) is not int for n in state['credits'])
            or any(type(n) is not int or not 0 <= n <= sources[i]['available_records'] for i, n in enumerate(state['emitted']))
            or sum(state['emitted']) != state['position']
            or any(not isinstance(group, str) or (group != '' and not re.fullmatch('[a-f0-9]{64}', group)) for group in state['last_groups'])
            or (state['status'] == 'awaiting_publication') != (state['position'] == view['total_available_source_records'])):
        raise ValueError('Sampler state counters, scope or cursor changed.')
    maximum = db.execute('SELECT MAX(sequence) FROM receipts').fetchone()[0] or 0
    if maximum != state['sequence']:
        raise ValueError('Sampler state and committed receipt sequence differ.')
    if maximum:
        receipt = _receipt(db, state, maximum)
        if (receipt['revision'] != state['last_receipt_revision']
                or receipt['start_position'] + receipt['record_count'] != state['position']
                or receipt['prefix_source_counts'] != state['emitted']):
            raise ValueError('Sampler state no longer matches its last receipt.')
    elif state['position'] != 0 or state['last_receipt_revision'] is not None:
        raise ValueError('Sampler initial receipt binding changed.')
    return state


def _receipt(db, state, sequence):
    row = db.execute('SELECT request_id,value FROM receipts WHERE sequence=?', (sequence,)).fetchone()
    if row is None: raise ValueError('Sampler receipt sequence is incomplete.')
    value = _json(row[1])
    total = state['review']['source_review']['total_available_source_records']
    if (value.get('format') != 'almg-stream-mixture-batch-receipt-v1' or type(value.get('schema_version')) is not int
            or value['schema_version'] != 1 or value.get('session_id') != state['id']
            or type(value.get('sequence')) is not int or value['sequence'] != sequence
            or value.get('request_id') != row[0] or not re.fullmatch('[a-f0-9]{32}', row[0])
            or value.get('review_revision') != state['review']['revision']
            or type(value.get('requested_limit')) is not int or not 1 <= value['requested_limit'] <= MAX_BATCH
            or type(value.get('start_position')) is not int or not 0 <= value['start_position'] < total
            or type(value.get('record_count')) is not int
            or value['record_count'] != min(value['requested_limit'], total - value['start_position'])
            or not isinstance(value.get('references'), list) or len(value['references']) != value['record_count']
            or any('text' in reference for reference in value['references'])
            or not isinstance(value.get('payload_sha256'), str) or not re.fullmatch('[a-f0-9]{64}', value['payload_sha256'])
            or type(value.get('source_pass_complete')) is not bool
            or value['source_pass_complete'] != (value['start_position'] + value['record_count'] == total)):
        raise ValueError('Sampler receipt identity, count or payload binding changed.')
    return value


def _bindings(root, state):
    stored = state['review']['source_review']
    current = sampling._context(root, stored['mixture_id'])
    for key in ('mixture_id', 'mixture_revision', 'split', 'sources', 'total_available_source_records', 'method'):
        if current[key] != stored[key]:
            raise ValueError('Sampler source or declaration bindings changed; committed batches are preserved.')
    return current


def begin(root, mixture_id, confirmed, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm a separate durable record session; no model training is approved.')
    current = _review(root, mixture_id)
    if not isinstance(reviewed, dict) or current != reviewed:
        raise ValueError('Session review changed. Reopen the exact source/declaration review.')
    count = len(current['source_review']['sources'])
    state = _seal({'format': 'almg-stream-mixture-session-v1', 'schema_version': 1, 'id': uuid.uuid4().hex,
                   'status': 'active', 'review': current, 'position': 0, 'sequence': 0,
                   'emitted': [0] * count, 'credits': [0] * count, 'last_groups': [''] * count,
                   'last_receipt_revision': None, **{flag: False for flag in FLAGS}})
    parent = _folder(root, state['id']).parent
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.session-', dir=parent) as temporary:
        staged = Path(temporary) / state['id'];staged.mkdir()
        with sampling.indexes._connect(staged / 'session.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
            db.execute('CREATE TABLE receipts(sequence INTEGER PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,value TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(state, allow_nan=False),))
        if _review(root, mixture_id) != current:
            raise ValueError('Session bindings changed during preparation.')
        staged.rename(parent / state['id'])
    return state


def read(root, session_id):
    directory = _folder(root, session_id)
    try:
        with sampling.indexes._connect(directory / 'session.sqlite3', True) as db:state = _state(db)
        if state['id'] != session_id: raise ValueError('Sampler session identity changed.')
        _bindings(root, state)
        path = directory / 'manifest.json'
        if path.exists():
            if path.stat().st_size > MAX_JSON: raise ValueError('Sampler manifest exceeds its size limit.')
            manifest = _json(path.read_text(encoding='utf-8'))
            expected = _seal({**state, 'status': 'complete', 'files': {'session.sqlite3': file_digest(directory / 'session.sqlite3')}})
            if state['status'] != 'awaiting_publication' or manifest != expected:
                raise ValueError('Sampler completed manifest or receipt database changed.')
            return manifest
        return state
    except (OSError, sqlite3.Error, TypeError, KeyError, AttributeError) as error:
        raise ValueError('Sampler session is unavailable or incomplete.') from error


def _record(source, row, position):
    group, text, split, line, offset, raw, occurrences = row
    return {'position': position, 'text': text, 'group': group, 'split': split,
            **{key: source[key] for key in ('index_id', 'index_revision', 'source_id', 'source_sha256', 'declaration_revision', 'declaration_basis')},
            'first_line': line, 'first_byte_offset': offset, 'raw_line_sha256': raw, 'occurrences': occurrences}


def _payload(root, state, receipt):
    view = _bindings(root, state)
    signatures = sampling.overlap._signatures(sampling._paths(root, view))
    records = []
    with ExitStack() as stack:
        databases = {source['index_id']: (source, stack.enter_context(sampling.indexes._connect(
            sampling.indexes._folder(root, source['index_id']) / 'records.sqlite3', True))) for source in view['sources']}
        for i, reference in enumerate(receipt['references']):
            source, db = databases[reference['index_id']]
            row = db.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences '
                             'FROM documents WHERE group_sha256=? AND split=?', (reference['group'], 'train')).fetchone()
            if row is None: raise ValueError('A committed source record is unavailable.')
            record = _record(source, row, receipt['start_position'] + i)
            if {key: value for key, value in record.items() if key != 'text'} != reference:
                raise ValueError('A committed source reference changed.')
            records.append(record)
    _bindings(root, state)
    if sampling.overlap._signatures(sampling._paths(root, view)) != signatures or digest(records) != receipt['payload_sha256']:
        raise ValueError('Committed sampler payload no longer matches its receipt.')
    return {'format': 'almg-stream-mixture-session-batch-v1', 'schema_version': 1,
            'session_id': state['id'], 'receipt': receipt, 'records': records, **{flag: False for flag in FLAGS}}


def batch(root, session_id, confirmed, sequence):
    if confirmed is not True: raise ValueError('Confirm replaying private source text from a committed batch.')
    if type(sequence) is not int or sequence < 1: raise ValueError('Choose a committed positive batch sequence.')
    with _LOCK:
        state = read(root, session_id)
        with sampling.indexes._connect(_folder(root, session_id) / 'session.sqlite3', True) as db:
            receipt = _receipt(db, state, sequence)
        return _payload(root, state, receipt)


def _commit(db, state, receipt):
    db.execute('INSERT INTO receipts VALUES(?,?,?)', (receipt['sequence'], receipt['request_id'], json.dumps(receipt, allow_nan=False)))
    db.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(state, allow_nan=False),))


def _publish(root, state):
    _bindings(root, state)
    directory = _folder(root, state['id'])
    with sampling.indexes._connect(directory / 'session.sqlite3', True) as db:
        previous, position = None, 0
        for sequence in range(1, state['sequence'] + 1):
            receipt = _receipt(db, state, sequence)
            if receipt['previous_revision'] != previous or receipt['start_position'] != position:
                raise ValueError('Sampler receipt chain is incomplete.')
            previous = receipt['revision'];position += receipt['record_count']
        if previous != state['last_receipt_revision'] or position != state['position']:
            raise ValueError('Sampler final cursor differs from its receipt chain.')
    manifest = _seal({**state, 'status': 'complete', 'files': {'session.sqlite3': file_digest(directory / 'session.sqlite3')}})
    temporary = directory / (uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        temporary.replace(directory / 'manifest.json')
    finally: temporary.unlink(missing_ok=True)
    return manifest


def step(root, session_id, confirmed, request_id, limit=16):
    if confirmed is not True: raise ValueError('Confirm the next durable source-record batch; no training is approved.')
    if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id):
        raise ValueError('Provide a stable UUID request ID so retries cannot skip a batch.')
    if type(limit) is not int or not 1 <= limit <= MAX_BATCH: raise ValueError('Choose one to 16 source records per batch.')
    with _LOCK:
        visible = read(root, session_id)
        with sampling.indexes._connect(_folder(root, session_id) / 'session.sqlite3') as db:
            db.execute('BEGIN IMMEDIATE');state = _state(db)
            saved = db.execute('SELECT sequence FROM receipts WHERE request_id=?', (request_id,)).fetchone()
            if saved:
                receipt = _receipt(db, state, saved[0])
                if receipt['requested_limit'] != limit: raise ValueError('This request ID already binds a different batch size.')
            else:
                if state['status'] != 'active': raise ValueError('The source pass is exhausted; replay an existing receipt instead.')
                if _review(root, state['review']['mixture_id']) != state['review']:
                    raise ValueError('Sampler implementation/runtime or review changed; preserve this session and review a new one.')
                view = _bindings(root, state);sources = view['sources']
                signatures = sampling.overlap._signatures(sampling._paths(root, view))
                records = [];start = state['position']
                with ExitStack() as stack:
                    databases = [stack.enter_context(sampling.indexes._connect(sampling.indexes._folder(root, source['index_id']) / 'records.sqlite3', True)) for source in sources]
                    pending = [sampling._next(db_source, state['last_groups'][i]) for i, db_source in enumerate(databases)]
                    for _ in range(min(limit, view['total_available_source_records'] - start)):
                        active = [i for i, row in enumerate(pending) if row is not None]
                        if not active: raise ValueError('Sampler sources exhausted before their reviewed counts.')
                        for i in active: state['credits'][i] += sources[i]['weight']
                        chosen = max(active, key=lambda i: (state['credits'][i], -i))
                        state['credits'][chosen] -= sum(sources[i]['weight'] for i in active)
                        row = pending[chosen];records.append(_record(sources[chosen], row, state['position']))
                        state['position'] += 1;state['emitted'][chosen] += 1;state['last_groups'][chosen] = row[0]
                        pending[chosen] = sampling._next(databases[chosen], row[0])
                        if ((pending[chosen] is None) != (state['emitted'][chosen] == sources[chosen]['available_records'])
                                or state['emitted'][chosen] > sources[chosen]['available_records']):
                            raise ValueError('Sampler source count differs from its reviewed capacity.')
                _bindings(root, state)
                if sampling.overlap._signatures(sampling._paths(root, view)) != signatures:
                    raise ValueError('Source or declaration files changed; this batch was not committed.')
                state['sequence'] += 1
                complete = state['position'] == view['total_available_source_records']
                receipt = _seal({'format': 'almg-stream-mixture-batch-receipt-v1', 'schema_version': 1,
                    'session_id': state['id'], 'sequence': state['sequence'], 'request_id': request_id,
                    'review_revision': state['review']['revision'], 'requested_limit': limit, 'start_position': start,
                    'record_count': len(records), 'references': [{k: v for k, v in record.items() if k != 'text'} for record in records],
                    'payload_sha256': digest(records), 'prefix_source_counts': list(state['emitted']),
                    'source_pass_complete': complete, 'previous_revision': state['last_receipt_revision']})
                state['last_receipt_revision'] = receipt['revision']
                state['status'] = 'awaiting_publication' if complete else 'active';_seal(state)
                _commit(db, state, receipt)
                _bindings(root, state)
                if sampling.overlap._signatures(sampling._paths(root, view)) != signatures:
                    raise ValueError('Source declarations changed before commit; this batch was rolled back.')
        if state['status'] == 'awaiting_publication' and visible['status'] != 'complete': _publish(root, state)
        return _payload(root, state, receipt)
