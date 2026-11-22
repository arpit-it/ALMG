import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_mixtures as mixtures, decoder_stream_mixture_overlap as overlap, studio
from backend.run_manifest import digest, file_digest


class MixtureOverlapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def source(self, name, shared=()):
        rows = [f'{name} local document number {i}' for i in range(100)] + list(shared)
        data = ('\n'.join(rows) + '\n').encode()
        source = streams.create(self.root, name + '.txt', len(data), hashlib.sha256(data).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(data).decode(), True)
        streams.seal(self.root, source['id'], True)
        record = indexes.begin(self.root, source['id'], True)
        return indexes.step(self.root, record['id'], True)

    def plan(self, sources):
        reviewed = mixtures.review(self.root, True, [{'index_id': source['id'], 'weight': i + 1}
                                                    for i, source in enumerate(sources)])
        return mixtures.save(self.root, True, reviewed)

    def inspect(self, plan):
        return overlap.review(self.root, plan['id'], True, plan)

    def test_complete_pair_counts_bounded_samples_and_source_provenance_without_writes(self):
        shared = [f'shared orchard example number {i}' for i in range(12)]
        sources = [self.source('one', shared + [shared[0]]), self.source('two', shared), self.source('three', shared)]
        plan = self.plan(sources)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.inspect(plan)
        self.assertEqual(result['source_pairs_checked'], 3)
        self.assertEqual(result['exact_overlap_record_pairs'], 36)  # Pairs, not 12 globally distinct groups.
        self.assertEqual(result['cross_split_record_pairs'], 0)
        expected_groups = {digest(text) for text in shared}
        for pair in result['pairs']:
            self.assertEqual(pair['exact_overlap_record_pairs'], 12)
            self.assertEqual(pair['findings_omitted'], 7)
            self.assertEqual(len(pair['findings_sample']), 5)
            self.assertEqual(sum(row['record_pairs'] for row in pair['split_pair_counts']), 12)
            for finding in pair['findings_sample']:
                self.assertIn(finding['group_sha256'], expected_groups)
                self.assertFalse(finding['cross_split'])
                for side in ('left', 'right'):
                    source = next(source for source in sources if source['id'] == pair[side + '_index_id'])
                    with indexes._connect(indexes._folder(self.root, source['id']) / 'records.sqlite3', True) as db:
                        row = db.execute('SELECT split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents WHERE group_sha256=?', (finding['group_sha256'],)).fetchone()
                    self.assertEqual(finding[side], dict(zip(('split', 'first_line', 'first_byte_offset', 'raw_line_sha256', 'occurrences'), row)))
        self.assertFalse(result['training_approved'])
        self.assertFalse(result['near_duplicate_contamination_checked'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(self.inspect(plan), result)
        self.assertNotIn('shared orchard example', json.dumps(result))

    def test_disjoint_sources_return_zero_without_claiming_comprehensive_contamination_clearance(self):
        result = self.inspect(self.plan([self.source('alpha'), self.source('beta')]))
        self.assertEqual(result['exact_overlap_record_pairs'], 0)
        self.assertEqual(result['pairs'][0]['findings_sample'], [])
        self.assertTrue(result['exact_cross_source_overlap_checked'])
        self.assertFalse(result['permission_reviewed'])

    def test_cross_split_fixture_checks_all_splits_and_prioritizes_affected_records(self):
        shared = ['shared evaluation fixture'] + [f'common example {i}' for i in range(10)]
        first, second = self.source('first', shared), self.source('second', shared)
        group = digest(shared[0])
        # Deliberate fixture with a saved alternate split assignment. Count the
        # stored labels rather than assuming all old/custom indexes use today's policy.
        directory = indexes._folder(self.root, second['id'])
        with indexes._connect(directory / 'records.sqlite3') as db:
            old_split = db.execute('SELECT split FROM documents WHERE group_sha256=?', (group,)).fetchone()[0]
            new_split = 'test' if old_split != 'test' else 'validation'
            db.execute('UPDATE documents SET split=? WHERE group_sha256=?', (new_split, group))
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['split_counts'][old_split] -= 1
        manifest['split_counts'][new_split] += 1
        manifest['files']['records.sqlite3'] = file_digest(directory / 'records.sqlite3')
        manifest['revision'] = digest({k: v for k, v in manifest.items() if k != 'revision'})
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        second = indexes.read(self.root, second['id'])
        result = self.inspect(self.plan([first, second]))
        self.assertEqual(result['cross_split_record_pairs'], 1)
        self.assertEqual(result['pairs'][0]['findings_sample'][0]['group_sha256'], group)
        self.assertTrue(result['pairs'][0]['findings_sample'][0]['cross_split'])
        self.assertEqual(result['exact_overlap_record_pairs'], 11)

    def test_consent_and_stale_review_reject(self):
        plan = self.plan([self.source('alpha'), self.source('beta')])
        with self.assertRaises(ValueError): overlap.review(self.root, plan['id'], False, plan)
        stale = deepcopy(plan)
        stale['review']['sources'][0]['weight'] += 1
        for value in (None, stale):
            with self.assertRaisesRegex(ValueError, 'review changed'): overlap.review(self.root, plan['id'], True, value)

    def test_corrupt_source_and_file_changes_during_scan_reject_without_a_report(self):
        sources = [self.source('alpha', ['shared record']), self.source('beta', ['shared record'])]
        plan = self.plan(sources)
        path = indexes._folder(self.root, sources[0]['id']) / 'records.sqlite3'
        original = path.read_bytes()
        with path.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): self.inspect(plan)
        path.write_bytes(original)
        signatures = overlap._signatures
        calls = 0

        def touch_during_query(paths):
            nonlocal calls
            calls += 1
            if calls == 4: path.touch()
            return signatures(paths)

        with patch.object(overlap, '_signatures', side_effect=touch_during_query):
            with self.assertRaisesRegex(ValueError, 'files changed'): self.inspect(plan)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(mixtures.read(self.root, plan['id']), plan)

    def test_sqlite_failure_is_not_a_partial_success(self):
        plan = self.plan([self.source('alpha'), self.source('beta')])
        with patch.object(overlap.sqlite3, 'connect', side_effect=sqlite3.OperationalError('fixture unavailable')):
            with self.assertRaises(ValueError): self.inspect(plan)

    def test_app_route_dispatches_confirmed_saved_plan(self):
        plan = self.plan([self.source('alpha', ['common record']), self.source('beta', ['common record'])])
        raw = json.dumps({'confirmed': True, 'reviewed': plan}).encode()
        handler = Mock(path='/decoder-stream-mixtures/' + plan['id'] + '/exact-overlap-review',
                       headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
        handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
        result = handler.respond.call_args.args[0]
        self.assertEqual(result['exact_overlap_record_pairs'], 1)
        self.assertEqual(result['mixture_revision'], plan['revision'])
