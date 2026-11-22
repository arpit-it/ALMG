"""Bounded read-only pages of every exact-overlap record pair in a saved mixture."""
from contextlib import closing
from itertools import combinations
from pathlib import Path
import re
import sqlite3

if __package__:
    from . import decoder_stream_mixture_overlap as overlap, decoder_stream_mixtures as mixtures
    from . import decoder_stream_indexes as indexes
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixture_overlap as overlap
    import decoder_stream_mixtures as mixtures
    import decoder_stream_indexes as indexes
    from run_manifest import digest, file_digest


def record_page(root, mixture_id, confirmed, reviewed, reviewed_report, cursor=None, limit=20):
    if confirmed is not True:
        raise ValueError('Confirm local overlap finding review; source record references are private.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Choose one to 100 overlap findings per page.')
    report = overlap.review(root, mixture_id, True, reviewed)
    if not isinstance(reviewed_report, dict) or report != reviewed_report:
        raise ValueError('The overlap report changed. Reopen it before reading findings.')
    reader = digest({name: file_digest(Path(__file__).with_name(name)) for name in
                     ('decoder_stream_mixture_findings.py', 'decoder_stream_mixture_overlap.py',
                      'decoder_stream_mixtures.py', 'decoder_stream_indexes.py')})
    sources = reviewed['review']['sources']
    pairs = list(combinations(range(len(sources)), 2))
    start, after = 0, ''
    binding = {'format': 'almg-stream-mixture-findings-cursor-v1',
               'mixture_revision': report['mixture_revision'], 'report_revision': report['revision'],
               'reader_sha256': reader}
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != set(binding) | {'pair_index', 'after_group'}
                or any(cursor.get(key) != value for key, value in binding.items())
                or type(cursor.get('pair_index')) is not int or not 0 <= cursor['pair_index'] < len(pairs)
                or not isinstance(cursor.get('after_group'), str)
                or not re.fullmatch('[a-f0-9]{64}', cursor['after_group'])):
            raise ValueError('Overlap findings cursor is invalid or stale. Reopen the report.')
        start, after = cursor['pair_index'], cursor['after_group']
    paths = [mixtures._folder(root, mixture_id) / 'manifest.json']
    for source in sources:
        directory = indexes._folder(root, source['index_id'])
        paths.extend([directory / 'manifest.json', directory / 'records.sqlite3'])
    try:
        signatures = overlap._signatures(paths)

        def unchanged():
            if overlap._signatures(paths) != signatures:
                raise ValueError('Overlap source files changed while reading findings; discard this page.')

        if mixtures.read(root, mixture_id) != reviewed:
            raise ValueError('Mixture bindings changed before reading findings.')
        unchanged()
        findings = []
        with closing(sqlite3.connect(':memory:', uri=True, timeout=10)) as db:
            db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA query_only=ON')
            for position, source in enumerate(sources):
                path = indexes._folder(root, source['index_id']) / 'records.sqlite3'
                db.execute(f'ATTACH DATABASE ? AS source{position}', (path.as_uri() + '?mode=ro',))
                db.execute(f'PRAGMA source{position}.cache_size=-2048')
            for pair_index in range(start, len(pairs)):
                unchanged()
                left, right = pairs[pair_index]
                joined = (f'FROM source{left}.documents l JOIN source{right}.documents r '
                          'ON l.group_sha256=r.group_sha256')
                anchor = after if pair_index == start else ''
                if pair_index == start and cursor is not None:
                    if db.execute('SELECT 1 ' + joined + ' WHERE l.group_sha256=?', (anchor,)).fetchone() is None:
                        raise ValueError('Overlap findings cursor does not identify a saved record pair.')
                rows = db.execute(
                    'SELECT l.group_sha256,l.split,r.split,l.first_line,l.first_byte_offset,l.raw_line_sha256,l.occurrences,'
                    'r.first_line,r.first_byte_offset,r.raw_line_sha256,r.occurrences ' + joined +
                    ' WHERE l.group_sha256>? ORDER BY l.group_sha256 LIMIT ?',
                    (anchor, limit + 1 - len(findings))).fetchall()
                for row in rows:
                    findings.append({
                        'pair_index': pair_index, 'left_index_id': sources[left]['index_id'],
                        'right_index_id': sources[right]['index_id'],
                        'group_sha256': row[0], 'cross_split': row[1] != row[2],
                        'left': {'split': row[1], 'first_line': row[3], 'first_byte_offset': row[4],
                                 'raw_line_sha256': row[5], 'occurrences': row[6]},
                        'right': {'split': row[2], 'first_line': row[7], 'first_byte_offset': row[8],
                                  'raw_line_sha256': row[9], 'occurrences': row[10]},
                    })
                unchanged()
                if len(findings) > limit:
                    break
        if mixtures.read(root, mixture_id) != reviewed:
            raise ValueError('Mixture bindings changed while reading findings.')
        unchanged()
    except (OSError, sqlite3.Error) as error:
        raise ValueError('Overlap finding sources are unavailable; no valid page is available.') from error
    following = None
    if len(findings) > limit:
        last = findings[limit - 1]
        following = {**binding, 'pair_index': last['pair_index'], 'after_group': last['group_sha256']}
    return {
        'format': 'almg-stream-mixture-findings-page-v1', 'schema_version': 1,
        'mixture_id': mixture_id, 'mixture_revision': report['mixture_revision'],
        'report_revision': report['revision'], 'reader_sha256': reader,
        'records': findings[:limit], 'next_cursor': following,
        'total_exact_record_pairs': report['exact_overlap_record_pairs'],
        'method': {'order': 'source_pair_index_then_group_sha256', 'maximum_page_records': 100,
                   'lookahead_records': 1, 'raw_text_included': False, 'source_files_read_only': True},
        'scope': 'Read-only finding references across all saved splits. Each request revalidates the complete exact-overlap report and source bindings; it is not a cached or constant-time lookup. Cursor positions are not proof that a caller consumed earlier pages. This page grants no quality clearance or training approval.',
        'training_approved': False, 'release_approved': False,
    }
