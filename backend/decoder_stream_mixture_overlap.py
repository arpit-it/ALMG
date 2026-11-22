"""Read-only exact cross-source record diagnostics for a saved mixture plan."""
from contextlib import closing
from itertools import combinations
from pathlib import Path
import sqlite3

if __package__:
    from . import decoder_stream_mixtures as mixtures
    from . import decoder_stream_indexes as indexes
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixtures as mixtures
    import decoder_stream_indexes as indexes
    from run_manifest import digest, file_digest

SAMPLE_LIMIT = 5


def _signatures(paths):
    result = []
    for path in paths:
        stat = path.stat()
        result.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
    return result


def review(root, mixture_id, confirmed, reviewed):
    if confirmed is not True:
        raise ValueError('Confirm exact cross-source overlap inspection of this saved mixture plan.')
    current = mixtures.read(root, mixture_id)
    if not isinstance(reviewed, dict) or reviewed != current:
        raise ValueError('The mixture review changed. Reopen the exact saved plan.')
    sources = current['review']['sources']
    paths = [mixtures._folder(root, mixture_id) / 'manifest.json']
    for source in sources:
        directory = indexes._folder(root, source['index_id'])
        paths.extend([directory / 'manifest.json', directory / 'records.sqlite3'])
    try:
        signatures = _signatures(paths)

        def unchanged():
            if _signatures(paths) != signatures:
                raise ValueError('Mixture source files changed during overlap inspection; no report is valid.')

        if mixtures.read(root, mixture_id) != current:
            raise ValueError('Mixture bindings changed before overlap inspection.')
        unchanged()
        pairs = []
        with closing(sqlite3.connect(':memory:', uri=True, timeout=10)) as db:
            db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA query_only=ON')
            for position, source in enumerate(sources):
                database = indexes._folder(root, source['index_id']) / 'records.sqlite3'
                db.execute(f'ATTACH DATABASE ? AS source{position}', (database.as_uri() + '?mode=ro',))
                db.execute(f'PRAGMA source{position}.cache_size=-2048')
            for left, right in combinations(range(len(sources)), 2):
                unchanged()
                # Aliases are generated integer positions, never caller-supplied SQL.
                joined = (f'FROM source{left}.documents l JOIN source{right}.documents r '
                          'ON l.group_sha256=r.group_sha256')
                counts = db.execute('SELECT l.split,r.split,COUNT(*) ' + joined +
                                    ' GROUP BY l.split,r.split ORDER BY l.split,r.split').fetchmany(10)
                if len(counts) > 9 or any(a not in ('train', 'validation', 'test') or b not in ('train', 'validation', 'test')
                       for a, b, _ in counts):
                    raise ValueError('An overlapping record has an unsupported saved split.')
                rows = db.execute(
                    'SELECT l.group_sha256,l.split,r.split,l.first_line,l.first_byte_offset,l.raw_line_sha256,l.occurrences,'
                    'r.first_line,r.first_byte_offset,r.raw_line_sha256,r.occurrences ' + joined +
                    ' ORDER BY (l.split<>r.split) DESC,l.group_sha256 LIMIT ?', (SAMPLE_LIMIT,)).fetchall()
                findings = []
                for row in rows:
                    findings.append({
                        'group_sha256': row[0], 'cross_split': row[1] != row[2],
                        'left': {'split': row[1], 'first_line': row[3], 'first_byte_offset': row[4],
                                 'raw_line_sha256': row[5], 'occurrences': row[6]},
                        'right': {'split': row[2], 'first_line': row[7], 'first_byte_offset': row[8],
                                  'raw_line_sha256': row[9], 'occurrences': row[10]},
                    })
                total = sum(count for _, _, count in counts)
                pairs.append({
                    'left_index_id': sources[left]['index_id'], 'right_index_id': sources[right]['index_id'],
                    'exact_overlap_record_pairs': total,
                    'cross_split_record_pairs': sum(count for a, b, count in counts if a != b),
                    'selected_split_record_pairs': sum(count for a, b, count in counts
                                                       if a == b == current['review']['split']),
                    'split_pair_counts': [{'left_split': a, 'right_split': b, 'record_pairs': count}
                                          for a, b, count in counts],
                    'findings_sample': findings, 'findings_omitted': total - len(findings),
                })
                unchanged()
        if mixtures.read(root, mixture_id) != current:
            raise ValueError('Mixture bindings changed during overlap inspection.')
        unchanged()
    except (OSError, sqlite3.Error) as error:
        raise ValueError('Mixture overlap inspection failed; no complete report is available.') from error
    report = {
        'format': 'almg-stream-mixture-exact-overlap-v1', 'schema_version': 1,
        'mixture_id': mixture_id, 'mixture_revision': current['revision'],
        'mixture_review_revision': current['review']['revision'],
        'sources': [{key: source[key] for key in
                     ('index_id', 'index_revision', 'index_file_sha256', 'source_id', 'source_sha256')}
                    for source in sources],
        'source_pairs_checked': len(pairs), 'pairs': pairs,
        'exact_overlap_record_pairs': sum(pair['exact_overlap_record_pairs'] for pair in pairs),
        'cross_split_record_pairs': sum(pair['cross_split_record_pairs'] for pair in pairs),
        'method': {'version': 1, 'identity': 'saved_normalized_text_sha256',
                   'population': 'all_unordered_source_pairs_all_saved_splits',
                   'source_occurrences_expanded': False, 'sample_limit_per_source_pair': SAMPLE_LIMIT,
                   'sample_order': 'cross_split_first_then_group_sha256',
                   'sqlite_cache_kib_per_source': 2048, 'temporary_storage': 'file',
                   'raw_text_included': False, 'source_files_read_only': True},
        'exact_cross_source_overlap_checked': True, 'near_duplicate_contamination_checked': False,
        'permission_reviewed': False, 'sampling_executed': False,
        'training_approved': False, 'release_approved': False,
        'scope': 'Complete exact normalized-hash counts, bounded finding samples only. Counts are record pairs per source pair, not globally distinct records; a record present in three sources counts in three pairs. Source splits are preserved and every split is checked, including splits outside the plan selection. Hash identity does not detect near-duplicates or semantic contamination. This read-only report does not deduplicate, filter, alter a saved plan or grant training approval.',
        'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                                         ('decoder_stream_mixture_overlap.py', 'decoder_stream_mixtures.py', 'decoder_stream_indexes.py')}),
    }
    report['revision'] = digest(report)
    return report
