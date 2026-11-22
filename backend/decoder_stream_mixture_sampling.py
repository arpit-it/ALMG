"""Bounded deterministic weighted training-record previews; never training admission."""
from contextlib import ExitStack
from pathlib import Path
import platform
import re
import sqlite3
import unicodedata

if __package__:
    from . import decoder_stream_mixtures as mixtures, decoder_stream_indexes as indexes
    from . import decoder_stream_permissions as permissions, decoder_stream_mixture_overlap as overlap
    from .decoder_tokenizer import Tokenizer
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixtures as mixtures
    import decoder_stream_indexes as indexes
    import decoder_stream_permissions as permissions
    import decoder_stream_mixture_overlap as overlap
    from decoder_tokenizer import Tokenizer
    from run_manifest import digest, file_digest

MAX_PREVIEW_RECORDS = 256
MAX_PAGE_RECORDS = 16


def _context(root, mixture_id):
    plan = mixtures.read(root, mixture_id)
    if plan['review']['split'] != 'train':
        raise ValueError('Weighted preview supports training-split plans only; held-out splits are not reweighted.')
    sources = []
    for source in plan['review']['sources']:
        declared = permissions.review(root, source['index_id'])
        latest = declared['latest_declaration']
        if latest is None or latest['basis'] not in ('user_created', 'permission_recorded'):
            raise ValueError('Every source needs a current user_created or permission_recorded declaration before weighted preview.')
        sources.append({**source, 'permission_review_revision': declared['revision'],
                        'declaration_revision': latest['revision'], 'declaration_sequence': latest['sequence'],
                        'declaration_basis': latest['basis']})
    result = {
        'format': 'almg-stream-mixture-sampling-review-v1', 'schema_version': 1,
        'mixture_id': mixture_id, 'mixture_revision': plan['revision'], 'split': 'train', 'sources': sources,
        'total_available_source_records': sum(source['available_records'] for source in sources),
        'method': {'version': 1, 'name': 'smooth_weighted_round_robin_without_replacement',
                   'within_source_order': 'group_sha256', 'tie_break': 'canonical_source_index_order',
                   'randomized': False, 'exhausted_sources': 'removed_weights_renormalize_for_remaining_sources',
                   'source_occurrences_expanded': False, 'cross_source_deduplication_applied': False,
                   'weight_effect': 'relative_prefix_interleaving_until_exhaustion_not_final_epoch_proportions'},
        'maximum_preview_records': MAX_PREVIEW_RECORDS, 'maximum_page_records': MAX_PAGE_RECORDS,
        'permission_verified': False, 'quality_clearance': False, 'training_approved': False, 'release_approved': False,
        'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version, 'unicode': unicodedata.unidata_version},
        'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                                         ('decoder_stream_mixture_sampling.py', 'decoder_stream_mixtures.py',
                                          'decoder_stream_indexes.py', 'decoder_stream_permissions.py',
                                          'decoder_stream_mixture_overlap.py', 'decoder_tokenizer.py', 'run_manifest.py')}),
        'scope': 'Private normalized-text sampling preview only. Weights affect source ordering, not within-source order. Each source contributes records once; final full-pass source counts follow source capacities rather than requested weights. Cross-source duplicates are retained with separate provenance. Current declarations are user statements, not verified permissions. Exact/near/semantic quality and training admission remain separate; no training or release is approved.',
    }
    result['revision'] = digest(result)
    return result


def review(root, mixture_id, confirmed, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm local mixture and source-declaration inspection before sampling review.')
    plan = mixtures.read(root, mixture_id)
    if not isinstance(reviewed, dict) or reviewed != plan:
        raise ValueError('Reopen the exact saved mixture before sampling review.')
    return _context(root, mixture_id)


def _paths(root, context):
    result = [mixtures._folder(root, context['mixture_id']) / 'manifest.json']
    for source in context['sources']:
        directory = indexes._folder(root, source['index_id'])
        result.extend([directory / 'manifest.json', directory / 'records.sqlite3'])
        declared = Path(root) / 'decoder-stream-permissions' / source['index_id']
        result.append(declared)
        result.extend(declared / f'{sequence:04}.json' for sequence in range(1, source['declaration_sequence'] + 1))
    return result


def _next(db, after):
    row = db.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences '
                     'FROM documents WHERE split=? AND group_sha256>? ORDER BY group_sha256 LIMIT 1', ('train', after)).fetchone()
    if row is not None:
        group, text, split, line, offset, raw, occurrences = row
        if (not isinstance(text, str) or ' '.join(Tokenizer.words(text)) != text or digest(text) != group or split != 'train'
                or type(line) is not int or line < 1 or type(offset) is not int or offset < 0
                or type(occurrences) is not int or occurrences < 1
                or not isinstance(raw, str) or not re.fullmatch('[a-f0-9]{64}', raw)):
            raise ValueError('A preview record no longer matches its normalized training-source contract.')
    return row


def preview(root, mixture_id, confirmed, reviewed, cursor=None, limit=8):
    if confirmed is not True:
        raise ValueError('Confirm previewing private normalized source text; this does not approve training.')
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_RECORDS:
        raise ValueError('Choose one to 16 training records per preview page.')
    current = _context(root, mixture_id)
    if not isinstance(reviewed, dict) or current != reviewed:
        raise ValueError('Sampling sources, declarations or implementation changed. Reopen sampling review.')
    end = min(MAX_PREVIEW_RECORDS, current['total_available_source_records'])
    after = 0
    binding = {'format': 'almg-stream-mixture-sampling-cursor-v1', 'review_revision': current['revision']}
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != set(binding) | {'after_records'}
                or any(cursor.get(key) != value for key, value in binding.items())
                or type(cursor.get('after_records')) is not int or not 0 < cursor['after_records'] < end):
            raise ValueError('Sampling cursor is invalid or stale. Reopen the first preview page.')
        after = cursor['after_records']
    paths = _paths(root, current)
    try:
        signatures = overlap._signatures(paths)

        def unchanged():
            if overlap._signatures(paths) != signatures:
                raise ValueError('Sampling source or declaration files changed; discard this preview page.')

        if _context(root, mixture_id) != current:
            raise ValueError('Sampling bindings changed before preview.')
        unchanged()
        sources = current['sources']
        credits, emitted = [0] * len(sources), [0] * len(sources)
        records = []
        stop = min(end, after + limit)
        with ExitStack() as stack:
            databases = [stack.enter_context(indexes._connect(indexes._folder(root, source['index_id']) / 'records.sqlite3', True))
                         for source in sources]
            pending = [_next(db, '') for db in databases]
            if any(row is None for row in pending):
                raise ValueError('A reviewed source has no available training records.')
            for position in range(stop):
                unchanged()
                active = [i for i, row in enumerate(pending) if row is not None]
                if not active:
                    raise ValueError('Training-record counts differ from the reviewed mixture.')
                for i in active:
                    credits[i] += sources[i]['weight']
                chosen = max(active, key=lambda i: (credits[i], -i))
                credits[chosen] -= sum(sources[i]['weight'] for i in active)
                row = pending[chosen]
                emitted[chosen] += 1
                if position >= after:
                    source = sources[chosen]
                    group, text, split, line, offset, raw, occurrences = row
                    records.append({'position': position, 'text': text, 'group': group, 'split': split,
                                    'index_id': source['index_id'], 'index_revision': source['index_revision'],
                                    'source_id': source['source_id'], 'source_sha256': source['source_sha256'],
                                    'first_line': line, 'first_byte_offset': offset, 'raw_line_sha256': raw,
                                    'occurrences': occurrences, 'declaration_revision': source['declaration_revision'],
                                    'declaration_basis': source['declaration_basis']})
                pending[chosen] = _next(databases[chosen], row[0])
                if pending[chosen] is None and emitted[chosen] != sources[chosen]['available_records']:
                    raise ValueError('A source exhausted before its reviewed training-record count.')
                if pending[chosen] is not None and emitted[chosen] >= sources[chosen]['available_records']:
                    raise ValueError('A source exceeds its reviewed training-record count.')
            if stop == current['total_available_source_records'] and any(row is not None for row in pending):
                raise ValueError('A source has more training records than its reviewed count.')
        if _context(root, mixture_id) != current:
            raise ValueError('Sampling bindings changed during preview; discard this page.')
        unchanged()
    except (OSError, sqlite3.Error) as error:
        raise ValueError('Sampling sources are unavailable; no preview page is valid.') from error
    complete = stop == current['total_available_source_records']
    return {
        'format': 'almg-stream-mixture-sampling-preview-v1', 'schema_version': 1,
        'mixture_id': mixture_id, 'sampling_review_revision': current['revision'],
        'records': records, 'next_cursor': {**binding, 'after_records': stop} if stop < end else None,
        'prefix_records_selected': stop, 'total_available_source_records': current['total_available_source_records'],
        'prefix_source_counts': [{'index_id': source['index_id'], 'records': emitted[i]} for i, source in enumerate(sources)],
        'source_pass_complete': complete, 'preview_limit_reached': stop == MAX_PREVIEW_RECORDS and not complete,
        'maximum_preview_records': MAX_PREVIEW_RECORDS,
        'permission_verified': False, 'quality_clearance': False, 'training_approved': False, 'release_approved': False,
        'scope': 'At most 256 deterministically interleaved training records, without replacement within each source. Every page replays its bounded prefix, not a cached or constant-time stream. A terminal cursor at the preview cap does not imply a complete source pass. Positions do not prove earlier records were consumed. User declarations and lexical diagnostics grant no training approval.',
    }
