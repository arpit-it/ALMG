"""Immutable private exact-overlap snapshots with bounded, verified history."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import threading
import uuid

if __package__:
    from . import decoder_stream_mixtures as mixtures, decoder_stream_mixture_overlap as overlap
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixtures as mixtures
    import decoder_stream_mixture_overlap as overlap
    from run_manifest import digest, file_digest

MAX_RECORDS = 32
MAX_BYTES = 256 * 1024
_LOCK = threading.RLock()


def _folder(root, mixture_id, audit_id=None):
    mixtures._folder(root, mixture_id)
    parent = Path(root) / 'decoder-stream-mixture-audits' / mixture_id
    if audit_id is None:
        return parent
    mixtures._folder(root, audit_id)
    return parent / audit_id


def _entries(root, mixture_id):
    parent = _folder(root, mixture_id)
    entries = []
    for path in parent.iterdir() if parent.exists() else []:
        if path.name.startswith('.audit-') and path.is_dir():
            continue
        if not re.fullmatch('[a-f0-9]{32}', path.name) or not path.is_dir():
            raise ValueError('Unexpected mixture audit history entry; existing evidence is preserved.')
        entries.append(path)
        if len(entries) > MAX_RECORDS:
            raise ValueError('Mixture audit history exceeds its supported bound; existing evidence is preserved.')
    return entries


def _compatible(saved, current):
    if (not isinstance(saved, dict) or type(saved.get('schema_version')) is not int
            or saved.get('revision') != digest({key: value for key, value in saved.items() if key != 'revision'})
            or not isinstance(saved.get('implementation_sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', saved['implementation_sha256'])):
        raise ValueError('Saved mixture overlap report integrity changed.')
    expected = {**current, 'implementation_sha256': saved['implementation_sha256']}
    expected['revision'] = digest({key: value for key, value in expected.items() if key != 'revision'})
    if expected != saved:
        raise ValueError('Saved mixture audit source bindings or versioned results changed.')


def _read(root, mixture_id, audit_id, current):
    path = _folder(root, mixture_id, audit_id) / 'manifest.json'
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Mixture audit manifest exceeds its size limit.')
        record = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(record, dict) or set(record) != {
                'format', 'schema_version', 'id', 'mixture_id', 'mixture_revision', 'created_at',
                'report', 'training_approved', 'release_approved', 'scope', 'implementation_sha256', 'revision'}
                or record['format'] != 'almg-saved-stream-mixture-exact-audit-v1'
                or type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['id'] != audit_id or record['mixture_id'] != mixture_id
                or record['mixture_revision'] != current['mixture_revision']
                or record['training_approved'] is not False or record['release_approved'] is not False
                or record['scope'] != 'private_exact_overlap_snapshot_only_no_training_approval'
                or not isinstance(record['implementation_sha256'], str)
                or not re.fullmatch('[a-f0-9]{64}', record['implementation_sha256'])
                or record['revision'] != digest({key: value for key, value in record.items() if key != 'revision'})):
            raise ValueError('Mixture audit manifest integrity or scope changed.')
        timestamp = datetime.fromisoformat(record['created_at'])
        if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError('Mixture audit timestamp requires UTC.')
        _compatible(record['report'], current)
        return record
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Saved mixture audit is unavailable or malformed.') from error


def _current(root, mixture_id):
    plan = mixtures.read(root, mixture_id)
    return plan, overlap.review(root, mixture_id, True, plan)


def read(root, mixture_id, audit_id):
    with _LOCK:
        _, current = _current(root, mixture_id)
        record = _read(root, mixture_id, audit_id, current)
        if _current(root, mixture_id)[1] != current:
            raise ValueError('Mixture sources changed while reopening the audit.')
        return record


def history(root, mixture_id):
    with _LOCK:
        _, current = _current(root, mixture_id)
        records = [_read(root, mixture_id, entry.name, current) for entry in _entries(root, mixture_id)]
        if _current(root, mixture_id)[1] != current:
            raise ValueError('Mixture sources changed while reading audit history.')
        summaries = [{key: record[key] for key in ('id', 'created_at', 'revision')} | {
            'report_revision': record['report']['revision'],
            'exact_overlap_record_pairs': record['report']['exact_overlap_record_pairs'],
            'cross_split_record_pairs': record['report']['cross_split_record_pairs'],
            'report_implementation_sha256': record['report']['implementation_sha256'],
        } for record in sorted(records, key=lambda value: (value['created_at'], value['id']))]
        return {'format': 'almg-stream-mixture-exact-audit-history-v1', 'schema_version': 1,
                'mixture_id': mixture_id, 'mixture_revision': current['mixture_revision'],
                'records': summaries, 'record_count': len(records), 'maximum_records': MAX_RECORDS,
                'history_complete': True, 'training_approved': False, 'release_approved': False}


def save(root, mixture_id, confirmed, reviewed, reviewed_report):
    if confirmed is not True:
        raise ValueError('Confirm saving this exact private overlap audit; training is not approved.')
    with _LOCK:
        current = overlap.review(root, mixture_id, True, reviewed)
        if not isinstance(reviewed_report, dict) or reviewed_report != current:
            raise ValueError('The overlap report changed. Reopen it before saving an audit.')
        entries = _entries(root, mixture_id)
        for entry in entries:
            _read(root, mixture_id, entry.name, current)
        if len(entries) >= MAX_RECORDS:
            raise ValueError('Mixture audit history is full; existing evidence is preserved.')
        record = {
            'format': 'almg-saved-stream-mixture-exact-audit-v1', 'schema_version': 1,
            'id': uuid.uuid4().hex, 'mixture_id': mixture_id, 'mixture_revision': current['mixture_revision'],
            'created_at': datetime.now(timezone.utc).isoformat(), 'report': current,
            'training_approved': False, 'release_approved': False,
            'scope': 'private_exact_overlap_snapshot_only_no_training_approval',
            'implementation_sha256': file_digest(Path(__file__)),
        }
        record['revision'] = digest(record)
        raw = json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        if len(raw) > MAX_BYTES:
            raise ValueError('Mixture audit manifest exceeds its size limit.')
        parent = _folder(root, mixture_id)
        parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.audit-', dir=parent) as temporary:
            staged = Path(temporary) / record['id']
            staged.mkdir()
            (staged / 'manifest.json').write_bytes(raw)
            if overlap.review(root, mixture_id, True, reviewed) != current:
                raise ValueError('Mixture sources changed during audit saving.')
            if len(_entries(root, mixture_id)) >= MAX_RECORDS:
                raise ValueError('Mixture audit history filled during saving; existing evidence is preserved.')
            staged.rename(parent / record['id'])
        return record
