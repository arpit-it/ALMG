import base64
from copy import deepcopy
import hashlib
from io import BytesIO
from itertools import combinations
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_mixtures as mixtures, decoder_stream_mixture_overlap as overlap
from backend import decoder_stream_mixture_findings as findings, studio
from backend.run_manifest import digest, file_digest


class MixtureFindingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.shared = [f'common local example {i}' for i in range(7)]
        self.sources = [self.source('alpha', self.shared + [self.shared[0]]),
                        self.source('beta', self.shared), self.source('gamma', self.shared), self.source('disjoint')]
        self.plan = self.save(self.sources)
        self.report = overlap.review(self.root, self.plan['id'], True, self.plan)

    def source(self, name, shared=()):
        data = ('\n'.join([f'{name} local document {i}' for i in range(100)] + list(shared)) + '\n').encode()
        source = streams.create(self.root, name + '.txt', len(data), hashlib.sha256(data).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(data).decode(), True)
        streams.seal(self.root, source['id'], True)
        index = indexes.begin(self.root, source['id'], True)
        return indexes.step(self.root, index['id'], True)

    def save(self, sources):
        review = mixtures.review(self.root, True, [{'index_id': source['id'], 'weight': 1} for source in sources])
        return mixtures.save(self.root, True, review)

    def page(self, cursor=None, limit=4):
        return findings.record_page(self.root, self.plan['id'], True, self.plan, self.report, cursor, limit)

    def test_exhaustive_pages_cross_pair_boundaries_without_omissions_or_duplicates(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        sources = self.plan['review']['sources']
        populated = {source['id'] for source in self.sources[:3]}
        groups = sorted(digest(text) for text in self.shared)
        expected = [(i, sources[a]['index_id'], sources[b]['index_id'], group)
                    for i, (a, b) in enumerate(combinations(range(4), 2))
                    if sources[a]['index_id'] in populated and sources[b]['index_id'] in populated
                    for group in groups]
        for limit in (1, 4, 7, 8, 100):
            cursor = None
            seen = []
            while True:
                page = self.page(cursor, limit)
                self.assertLessEqual(len(page['records']), limit)
                self.assertEqual(page['total_exact_record_pairs'], 21)
                self.assertFalse(page['training_approved'])
                seen.extend((row['pair_index'], row['left_index_id'], row['right_index_id'], row['group_sha256']) for row in page['records'])
                cursor = page['next_cursor']
                if cursor is None: break
            self.assertEqual(seen, expected)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_empty_findings_have_no_cursor(self):
        plan = self.save([self.sources[3], self.source('another')])
        report = overlap.review(self.root, plan['id'], True, plan)
        page = findings.record_page(self.root, plan['id'], True, plan, report)
        self.assertEqual(page['records'], [])
        self.assertIsNone(page['next_cursor'])
        self.assertEqual(page['total_exact_record_pairs'], 0)

    def test_consent_limits_and_changed_reports_reject(self):
        with self.assertRaises(ValueError): findings.record_page(self.root, self.plan['id'], False, self.plan, self.report)
        for limit in (True, 0, -1, 101, 1.5, '4', None):
            with self.assertRaises(ValueError): self.page(limit=limit)
        changed = deepcopy(self.report)
        changed['exact_overlap_record_pairs'] += 1
        for report in (None, changed):
            with self.assertRaisesRegex(ValueError, 'report changed'):
                findings.record_page(self.root, self.plan['id'], True, self.plan, report)

    def test_cursor_validation_and_reader_binding(self):
        cursor = self.page()['next_cursor']
        for change in ({'report_revision': 'changed'}, {'mixture_revision': 'changed'}, {'reader_sha256': 'changed'},
                       {'pair_index': True}, {'pair_index': -1}, {'pair_index': 6}, {'after_group': '../unsafe'},
                       {'extra': 1}, {'after_group': '0' * 64}):
            with self.assertRaises(ValueError): self.page({**cursor, **change})
        with patch.object(findings, 'file_digest', return_value='new-reader'):
            with self.assertRaisesRegex(ValueError, 'cursor is invalid or stale'): self.page(cursor)

    def test_cursor_cannot_be_reused_for_another_saved_mixture(self):
        cursor = self.page()['next_cursor']
        other = self.save(self.sources)
        report = overlap.review(self.root, other['id'], True, other)
        with self.assertRaisesRegex(ValueError, 'cursor is invalid or stale'):
            findings.record_page(self.root, other['id'], True, other, report, cursor)

    def test_record_provenance_and_cross_split_labels_are_preserved(self):
        source = self.sources[1]
        folder = indexes._folder(self.root, source['id'])
        group = digest(self.shared[0])
        with indexes._connect(folder / 'records.sqlite3') as db:
            original_split = db.execute('SELECT split FROM documents WHERE group_sha256=?', (group,)).fetchone()[0]
            replacement = 'test' if original_split != 'test' else 'validation'
            db.execute('UPDATE documents SET split=? WHERE group_sha256=?', (replacement, group))
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest['split_counts'][original_split] -= 1
        manifest['split_counts'][replacement] += 1
        manifest['files']['records.sqlite3'] = file_digest(folder / 'records.sqlite3')
        manifest['revision'] = digest({k: v for k, v in manifest.items() if k != 'revision'})
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        plan = self.save(self.sources)
        report = overlap.review(self.root, plan['id'], True, plan)
        page = findings.record_page(self.root, plan['id'], True, plan, report, limit=100)
        self.assertEqual(sum(row['cross_split'] for row in page['records']), 2)
        for row in page['records']:
            for side in ('left', 'right'):
                database = indexes._folder(self.root, row[side + '_index_id']) / 'records.sqlite3'
                with indexes._connect(database, True) as db:
                    expected = db.execute('SELECT split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256=?', (row['group_sha256'],)).fetchone()
                self.assertEqual(row[side], dict(zip(('split', 'first_line', 'first_byte_offset', 'raw_line_sha256', 'occurrences'), expected)))

    def test_source_corruption_and_concurrent_changes_reject(self):
        cursor = self.page()['next_cursor']
        path = indexes._folder(self.root, self.sources[0]['id']) / 'records.sqlite3'
        original = path.read_bytes()
        with path.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): self.page(cursor)
        path.write_bytes(original)
        connect = sqlite3.connect
        touched = False

        def trace(sql):
            nonlocal touched
            if ' WHERE l.group_sha256>' in sql and not touched:
                path.touch()
                touched = True

        def observed_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(trace)
            return connection

        with patch.object(findings.sqlite3, 'connect', side_effect=observed_connect):
            with self.assertRaisesRegex(ValueError, 'files changed'): self.page(cursor)
        self.assertTrue(touched)
        self.assertEqual(path.read_bytes(), original)

    def test_route_dispatch(self):
        raw = json.dumps({'confirmed': True, 'reviewed': self.plan, 'reviewed_report': self.report, 'limit': 3}).encode()
        handler = Mock(path='/decoder-stream-mixtures/' + self.plan['id'] + '/exact-overlap-findings',
                       headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
        handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
        result = handler.respond.call_args.args[0]
        self.assertEqual(len(result['records']), 3)
        self.assertIsNotNone(result['next_cursor'])
