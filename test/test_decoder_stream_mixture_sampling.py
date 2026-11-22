from collections import Counter
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_mixtures as mixtures, decoder_stream_permissions as permissions
from backend import decoder_stream_mixture_sampling as sampling, studio
from backend.run_manifest import digest


class MixtureSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.shared = next(f'shared original record {i}' for i in range(100) if int(digest(f'shared original record {i}')[:8], 16) % 100 < 80)
        self.sources = [self.source('left', 80), self.source('right', 80)]
        self.plan = self.make_plan(self.sources)
        self.review = sampling.review(self.root, self.plan['id'], True, self.plan)

    def source(self, name, count):
        rows = [f'{name} original record {i}' for i in range(count)] + [self.shared]
        raw = ('\n'.join(rows + [rows[0]]) + '\n').encode()
        source = streams.create(self.root, name + '.txt', len(raw), hashlib.sha256(raw).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(raw).decode(), True)
        streams.seal(self.root, source['id'], True)
        index = indexes.begin(self.root, source['id'], True)
        index = indexes.step(self.root, index['id'], True)
        self.declare(index, 'user_created', 'Locally generated fixture')
        return index

    def declare(self, index, basis, note):
        current = permissions.review(self.root, index['id'])
        return permissions.declare(self.root, index['id'], True, current, basis, note)

    def make_plan(self, sources, split='train'):
        selected = [{'index_id': source['id'], 'weight': weight} for source, weight in zip(sources, (1, 3))]
        return mixtures.save(self.root, True, mixtures.review(self.root, True, selected, split))

    def page(self, cursor=None, limit=8, reviewed=None):
        return sampling.preview(self.root, self.plan['id'], True, self.review if reviewed is None else reviewed, cursor, limit)

    def test_relative_prefix_weights_provenance_and_read_only_sources(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        page = self.page()
        counts = Counter(row['index_id'] for row in page['records'])
        self.assertEqual(counts, {self.sources[0]['id']: 2, self.sources[1]['id']: 6})
        for row in page['records']:
            source = next(source for source in self.sources if source['id'] == row['index_id'])
            original = (self.root / 'decoder-streams' / source['source_id'] / 'source.bin').read_bytes().splitlines(keepends=True)
            line = original[row['first_line'] - 1]
            self.assertEqual(row['text'], line.decode().strip())
            self.assertEqual(row['raw_line_sha256'], hashlib.sha256(line).hexdigest())
            self.assertEqual(row['first_byte_offset'], sum(map(len, original[:row['first_line'] - 1])))
            self.assertEqual(row['group'], digest(row['text']))
            self.assertEqual(row['split'], 'train')
            self.assertEqual(row['declaration_basis'], 'user_created')
        for flag in ('permission_verified', 'quality_clearance', 'training_approved', 'release_approved'):
            self.assertIs(page[flag], False)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_page_sizes_replay_the_same_full_source_pass_and_exhaustion(self):
        sequences = []
        for limit in (1, 3, 16):
            records, cursor = [], None
            while True:
                page = self.page(cursor, limit)
                self.assertLessEqual(len(page['records']), limit)
                records.extend(page['records'])
                cursor = page['next_cursor']
                if cursor is None: break
            self.assertTrue(page['source_pass_complete'])
            self.assertFalse(page['preview_limit_reached'])
            self.assertEqual(len(records), self.review['total_available_source_records'])
            self.assertEqual(Counter(row['index_id'] for row in records), {source['id']: source['split_counts']['train'] for source in self.sources})
            self.assertEqual(len({(row['index_id'], row['group']) for row in records}), len(records))
            self.assertEqual(sum(row['group'] == digest(self.shared) for row in records), 2)
            sequences.append(records)
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual(sequences[1], sequences[2])

    def test_missing_or_changed_declarations_invalidate_review_and_cursor(self):
        first = self.page()
        self.declare(self.sources[0], 'needs_review', 'Fixture declaration now requires review')
        with self.assertRaisesRegex(ValueError, 'current user_created'): self.page(first['next_cursor'])
        self.declare(self.sources[0], 'permission_recorded', 'Fixture permission note')
        current = sampling.review(self.root, self.plan['id'], True, self.plan)
        with self.assertRaisesRegex(ValueError, 'declarations or implementation changed'): self.page()
        with self.assertRaisesRegex(ValueError, 'cursor is invalid or stale'): self.page(first['next_cursor'], reviewed=current)
        fresh = self.page(reviewed=current)
        self.assertEqual([(row['index_id'], row['group']) for row in fresh['records']], [(row['index_id'], row['group']) for row in first['records']])
        path = self.root / 'decoder-stream-permissions' / self.sources[1]['id'] / '0001.json'
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'current user_created'): sampling.review(self.root, self.plan['id'], True, self.plan)

    def test_cursor_and_implementation_bindings(self):
        cursor = self.page()['next_cursor']
        for change in ({'after_records': True}, {'after_records': 0}, {'after_records': 256},
                       {'review_revision': 'changed'}, {'extra': 1}):
            with self.assertRaises(ValueError): self.page({**cursor, **change})
        other = self.make_plan(self.sources)
        other_review = sampling.review(self.root, other['id'], True, other)
        with self.assertRaises(ValueError): sampling.preview(self.root, other['id'], True, other_review, cursor)
        with patch.object(sampling, 'file_digest', return_value='changed-reader'):
            with self.assertRaisesRegex(ValueError, 'implementation changed'): self.page(cursor)

    def test_consent_and_page_limits_reject_before_source_inspection(self):
        with patch.object(sampling, '_context') as inspected:
            with self.assertRaises(ValueError): sampling.preview(self.root, self.plan['id'], False, self.review)
            for limit in (True, 0, 17, 1.5, '4', None):
                with self.assertRaises(ValueError): self.page(limit=limit)
            inspected.assert_not_called()
        with self.assertRaises(ValueError): sampling.review(self.root, self.plan['id'], False, self.plan)

    def test_held_out_splits_cannot_be_weighted(self):
        for split in ('validation', 'test'):
            plan = self.make_plan(self.sources, split)
            with self.assertRaisesRegex(ValueError, 'held-out splits are not reweighted'):
                sampling.review(self.root, plan['id'], True, plan)

    def test_actual_preview_cap_is_not_reported_as_a_complete_pass(self):
        sources = [self.source('large-left', 200), self.source('large-right', 200)]
        plan = self.make_plan(sources)
        reviewed = sampling.review(self.root, plan['id'], True, plan)
        self.assertGreater(reviewed['total_available_source_records'], 256)
        records, cursor = [], None
        while True:
            page = sampling.preview(self.root, plan['id'], True, reviewed, cursor, 16)
            records.extend(page['records']);cursor = page['next_cursor']
            if cursor is None: break
        self.assertEqual(len(records), 256)
        self.assertFalse(page['source_pass_complete'])
        self.assertTrue(page['preview_limit_reached'])
        self.assertEqual(len({(row['index_id'], row['group']) for row in records}), 256)

    def test_concurrent_declaration_change_returns_no_preview(self):
        connect = sqlite3.connect
        changed = False

        def trace(sql):
            nonlocal changed
            if 'FROM documents WHERE split=' in sql and not changed:
                changed = True
                self.declare(self.sources[0], 'user_created', 'Concurrent fixture update')

        def observed_connect(*args, **kwargs):
            db = connect(*args, **kwargs);db.set_trace_callback(trace);return db

        with patch.object(sampling.sqlite3, 'connect', side_effect=observed_connect):
            with self.assertRaisesRegex(ValueError, 'files changed'): self.page()
        self.assertTrue(changed)

    def test_app_review_and_preview_routes(self):
        for suffix, reviewed in (('sampling-review', self.plan), ('sampling-preview', self.review)):
            raw = json.dumps({'confirmed': True, 'reviewed': reviewed, 'limit': 4}).encode()
            handler = Mock(path='/decoder-stream-mixtures/' + self.plan['id'] + '/' + suffix,
                           headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            result = handler.respond.call_args.args[0]
            self.assertNotIn('error', result)
            if suffix == 'sampling-preview': self.assertEqual(len(result['records']), 4)
