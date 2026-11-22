import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_mixtures as mixtures, decoder_stream_mixture_near_overlap as near, studio
from backend.run_manifest import digest, file_digest


class MixtureNearOverlapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = ' '.join('token' + str(i) for i in range(30))
        self.variant = ' '.join(self.base.split()[:-1] + ['replacement5'])
        self.left = self.source('left', [self.base])
        self.right = self.source('right', [self.variant])
        self.plan = self.plan_for([self.left, self.right])

    def source(self, name, long_rows):
        private = []
        for i in range(100):
            value = f'{name} private row {i}'
            if int(digest(value)[:8], 16) % 100 < 80:
                private.append(value)
            if len(private) == 2: break
        data = ('\n'.join(long_rows + ['same exact local line'] + private) + '\n').encode()
        source = streams.create(self.root, name + '.txt', len(data), hashlib.sha256(data).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(data).decode(), True)
        streams.seal(self.root, source['id'], True)
        index = indexes.begin(self.root, source['id'], True)
        return indexes.step(self.root, index['id'], True)

    def plan_for(self, sources):
        return mixtures.save(self.root, True, mixtures.review(self.root, True,
            [{'index_id': source['id'], 'weight': i + 1} for i, source in enumerate(sources)]))

    def begin(self, plan=None):
        plan = self.plan if plan is None else plan
        return near.begin(self.root, plan['id'], True, plan)

    def complete(self, record):
        while record['status'] != 'complete':
            record = near.step(self.root, record['id'], True)
        return record

    def test_exhaustive_counts_cross_split_findings_and_no_source_mutation(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        record = self.complete(self.begin())
        self.assertEqual(record['total_pairs'], 16)
        self.assertEqual(record['processed_pairs'], 16)
        self.assertEqual(record['exact_pairs_skipped'], 1)
        self.assertEqual(record['short_pairs_skipped'], 14)
        self.assertEqual(record['compared_pairs'], 1)
        self.assertEqual(record['near_duplicate_pairs'], 1)
        self.assertEqual(record['cross_split_pairs'], 1)
        page = near.record_page(self.root, record['id'], True)
        self.assertIsNone(page['next_cursor'])
        finding = page['records'][0]
        self.assertAlmostEqual(finding['similarity'], 25 / 27, places=6)
        self.assertTrue(finding['cross_split'])
        self.assertEqual({row['group'] for row in finding['records']}, {digest(self.base), digest(self.variant)})
        self.assertEqual({row['split'] for row in finding['records']}, {'train', 'test'})
        self.assertFalse(record['training_approved'])
        self.assertFalse(record['method']['source_weights_applied'])
        self.assertNotIn('token0 token1', json.dumps(page))
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_bounded_pause_reopen_and_resume_exactly_once(self):
        record = self.begin()
        with patch.object(near, 'MAX_BATCH_PAIRS', 3):
            record = near.step(self.root, record['id'], True)
        self.assertEqual((record['status'], record['processed_pairs']), ('scanning', 3))
        self.assertEqual(near.read(self.root, record['id']), record)
        with self.assertRaises(ValueError): near.record_page(self.root, record['id'], True)
        complete = self.complete(record)
        self.assertEqual(complete['processed_pairs'], 16)
        self.assertEqual(complete['near_duplicate_pairs'], 1)
        database = near._folder(self.root, record['id']) / 'audit.sqlite3'
        before = database.read_bytes()
        self.assertEqual(near.step(self.root, record['id'], True), complete)
        self.assertEqual(database.read_bytes(), before)

    def test_source_pair_boundaries_and_character_budget(self):
        third = self.source('third', [' '.join('different' + str(i) for i in range(30))])
        record = self.begin(self.plan_for([self.left, self.right, third]))
        with patch.object(near, 'MAX_BATCH_CHARACTERS', 600):
            record = near.step(self.root, record['id'], True)
        self.assertGreater(record['processed_pairs'], 0)
        self.assertLess(record['processed_pairs'], record['total_pairs'])
        record = self.complete(record)
        self.assertEqual((record['source_pair_count'], record['total_pairs']), (3, 48))
        self.assertEqual(record['exact_pairs_skipped'], 3)
        self.assertEqual(record['compared_pairs'], 3)
        self.assertEqual(record['near_duplicate_pairs'], 1)

    def test_consent_stale_plan_and_runtime_changes_preserve_progress(self):
        with self.assertRaises(ValueError): near.begin(self.root, self.plan['id'], False, self.plan)
        stale = deepcopy(self.plan)
        stale['review']['sources'][0]['weight'] += 1
        with self.assertRaises(ValueError): near.begin(self.root, self.plan['id'], True, stale)
        record = self.begin()
        database = near._folder(self.root, record['id']) / 'audit.sqlite3'
        before = database.read_bytes()
        with self.assertRaises(ValueError): near.step(self.root, record['id'], False)
        with patch.object(near, '_implementation', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'implementation/runtime changed'): near.step(self.root, record['id'], True)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(near.read(self.root, record['id']), record)

    def test_interrupted_transaction_rolls_back_findings_and_cursor_together(self):
        record = self.begin()
        compare = near._compare

        def interrupted(*args):
            compare(*args)
            if args[1]['near_duplicate_pairs']:
                raise ValueError('Fixture interruption after processing a pair')

        with patch.object(near, '_compare', side_effect=interrupted):
            with self.assertRaisesRegex(ValueError, 'Fixture interruption'): near.step(self.root, record['id'], True)
        self.assertEqual(near.read(self.root, record['id']), record)
        with indexes._connect(near._folder(self.root, record['id']) / 'audit.sqlite3', True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM findings').fetchone()[0], 0)
        self.assertEqual(self.complete(record)['near_duplicate_pairs'], 1)

    def test_publication_failure_retries_without_reprocessing(self):
        record = self.begin()
        with patch.object(near, '_publish', side_effect=OSError('Fixture publication interruption')):
            with self.assertRaises(OSError): near.step(self.root, record['id'], True)
        pending = near.read(self.root, record['id'])
        self.assertEqual((pending['status'], pending['processed_pairs']), ('awaiting_publication', 16))
        database = near._folder(self.root, record['id']) / 'audit.sqlite3'
        before = file_digest(database)
        complete = self.complete(pending)
        self.assertEqual(complete['near_duplicate_pairs'], 1)
        self.assertEqual(complete['files']['audit.sqlite3'], before)

    def test_source_change_and_completed_database_tamper_reject(self):
        pending = self.begin()
        database = near._folder(self.root, pending['id']) / 'audit.sqlite3'
        before = database.read_bytes()
        source = indexes._folder(self.root, self.left['id']) / 'records.sqlite3'
        source.touch()
        with self.assertRaisesRegex(ValueError, 'source files changed'): near.step(self.root, pending['id'], True)
        self.assertEqual(database.read_bytes(), before)
        # New review/audit binds the changed file signature without mutating old progress.
        complete = self.complete(self.begin())
        artifact = near._folder(self.root, complete['id']) / 'audit.sqlite3'
        with artifact.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): near.read(self.root, complete['id'])

    def test_finding_pages_and_invalid_cursors(self):
        second_variant = ' '.join(self.base.split()[:-1] + ['replacement6'])
        right = self.source('multiple', [self.variant, second_variant])
        complete = self.complete(self.begin(self.plan_for([self.left, right])))
        page = near.record_page(self.root, complete['id'], True, limit=1)
        cursor = page['next_cursor']
        self.assertIsNotNone(cursor)
        second = near.record_page(self.root, complete['id'], True, cursor, 1)
        self.assertIsNone(second['next_cursor'])
        self.assertNotEqual(page['records'], second['records'])
        for changed in ({**cursor, 'revision': 'changed'}, {**cursor, 'pair_index': True}, {**cursor, 'left_group': '0' * 64}):
            with self.assertRaises(ValueError): near.record_page(self.root, complete['id'], True, changed)
        for limit in (True, 0, 21):
            with self.assertRaises(ValueError): near.record_page(self.root, complete['id'], True, limit=limit)
        with self.assertRaises(ValueError): near.record_page(self.root, complete['id'], False)

    def test_app_begin_step_read_and_findings_routes(self):
        def post(path, values):
            raw = json.dumps(values).encode()
            handler = Mock(path=path, headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            return handler.respond.call_args.args[0]
        record = post('/decoder-stream-mixtures/' + self.plan['id'] + '/near-overlap-audits', {'confirmed': True, 'reviewed': self.plan})
        route = '/decoder-stream-mixture-near-overlap/' + record['id']
        complete = post(route + '/step', {'confirmed': True})
        self.assertEqual(complete['status'], 'complete')
        handler = Mock(path=route)
        handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_GET(handler)
        self.assertEqual(handler.respond.call_args.args[0], complete)
        self.assertEqual(len(post(route + '/records', {'confirmed': True})['records']), 1)
