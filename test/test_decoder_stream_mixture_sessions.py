from copy import deepcopy
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, patch

import test_decoder_stream_mixture_sampling as fixture_helpers
from backend import decoder_stream_mixture_sessions as sessions, decoder_stream_mixture_sampling as sampling, studio
from backend.run_manifest import file_digest


class MixtureSessionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_helpers.MixtureSamplingTests(methodName='runTest')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root, self.plan = self.fixture.root, self.fixture.plan
        self.review = sessions.review(self.root, self.plan['id'], True, self.plan)

    def begin(self):
        return sessions.begin(self.root, self.plan['id'], True, self.review)

    def step(self, state, request='a' * 32, limit=16):
        return sessions.step(self.root, state['id'], True, request, limit)

    def complete(self, state):
        packets = []
        while state['status'] != 'complete':
            packets.append(self.step(state, f"{state['sequence'] + 1:032x}"))
            state = sessions.read(self.root, state['id'])
        return state, packets

    def test_chunked_pass_matches_existing_preview_and_keeps_source_files_unchanged(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        state, packets = self.complete(self.begin())
        expected, cursor = [], None
        while True:
            page = sampling.preview(self.root, self.plan['id'], True, self.fixture.review, cursor, 16)
            expected.extend(page['records']);cursor = page['next_cursor']
            if cursor is None: break
        records = [row for packet in packets for row in packet['records']]
        self.assertEqual(records, expected)
        self.assertEqual(state['position'], len(expected))
        self.assertEqual(state['emitted'], [source['available_records'] for source in self.review['source_review']['sources']])
        self.assertEqual(len({(row['index_id'], row['group']) for row in records}), len(records))
        previous = None
        for packet in packets:
            self.assertEqual(packet['receipt']['previous_revision'], previous)
            previous = packet['receipt']['revision']
            self.assertFalse(packet['training_approved'])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_retry_and_historical_receipt_replay_never_advance_twice(self):
        state = self.begin();first = self.step(state, limit=8)
        database = sessions._folder(self.root, state['id']) / 'session.sqlite3'
        before = database.read_bytes()
        self.assertEqual(self.step(state, limit=8), first)
        self.assertEqual(database.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'different batch size'): self.step(state, limit=4)
        self.assertEqual(sessions.batch(self.root, state['id'], True, 1), first)
        self.step(state, 'b' * 32, 8)
        self.assertEqual(self.step(state, limit=8), first)
        self.assertEqual(sessions.read(self.root, state['id'])['position'], 16)
        with self.assertRaises(ValueError): sessions.batch(self.root, state['id'], True, 999)

    def test_transaction_failure_rolls_back_both_cursor_and_receipt(self):
        state = self.begin();commit = sessions._commit

        def interrupted(*args):
            commit(*args)
            raise ValueError('Fixture transport interruption before commit')

        with patch.object(sessions, '_commit', side_effect=interrupted):
            with self.assertRaises(ValueError): self.step(state)
        self.assertEqual(sessions.read(self.root, state['id']), state)
        packet = self.step(state)
        self.assertEqual(packet['receipt']['sequence'], 1)
        self.assertEqual(packet['receipt']['start_position'], 0)

    def test_publication_failure_replays_the_last_receipt_without_new_work(self):
        state = self.begin()
        while self.review['source_review']['total_available_source_records'] - state['position'] > 16:
            self.step(state, f"{state['sequence'] + 1:032x}")
            state = sessions.read(self.root, state['id'])
        request = f"{state['sequence'] + 1:032x}"
        with patch.object(sessions, '_publish', side_effect=OSError('Fixture publication interruption')):
            with self.assertRaises(OSError): self.step(state, request)
        pending = sessions.read(self.root, state['id'])
        self.assertEqual(pending['status'], 'awaiting_publication')
        database = sessions._folder(self.root, state['id']) / 'session.sqlite3';before = file_digest(database)
        packet = self.step(state, request)
        complete = sessions.read(self.root, state['id'])
        self.assertEqual(complete['status'], 'complete')
        self.assertEqual(packet, sessions.batch(self.root, state['id'], True, pending['sequence']))
        self.assertEqual(complete['files']['session.sqlite3'], before)
        with self.assertRaisesRegex(ValueError, 'source pass is exhausted'): self.step(state, 'f' * 32)

    def test_scope_validation_and_old_producer_receipts(self):
        with self.assertRaises(ValueError): sessions.begin(self.root, self.plan['id'], False, self.review)
        stale = deepcopy(self.review);stale['preview_cap_applied'] = True
        with self.assertRaises(ValueError): sessions.begin(self.root, self.plan['id'], True, stale)
        state = self.begin();first = self.step(state)
        for request, limit in ((True, 16), ('bad', 16), ('b' * 32, True), ('b' * 32, 17)):
            with self.assertRaises(ValueError): self.step(state, request, limit)
        with self.assertRaises(ValueError): sessions.step(self.root, state['id'], False, 'b' * 32)
        with self.assertRaises(ValueError): sessions.batch(self.root, state['id'], False, 1)
        with self.assertRaises(ValueError): sessions.batch(self.root, state['id'], True, True)
        with patch.object(sessions, 'file_digest', return_value='new-producer'):
            self.assertEqual(sessions.batch(self.root, state['id'], True, 1), first)
            with self.assertRaisesRegex(ValueError, 'implementation/runtime or review changed'): self.step(state, 'b' * 32)

    def test_complete_source_pass_exceeds_preview_cap_without_persisting_text(self):
        sources = [self.fixture.source('full-left', 200), self.fixture.source('full-right', 200)]
        self.plan = self.fixture.make_plan(sources)
        self.review = sessions.review(self.root, self.plan['id'], True, self.plan)
        self.assertIsNone(self.review['source_pass_record_limit'])
        self.assertGreater(self.review['source_review']['total_available_source_records'], 256)
        state, packets = self.complete(self.begin())
        records = [record for packet in packets for record in packet['records']]
        self.assertGreater(len(records), 256)
        self.assertEqual(len(records), self.review['source_review']['total_available_source_records'])
        source_review = sampling.review(self.root, self.plan['id'], True, self.plan)
        preview, cursor = [], None
        while True:
            page = sampling.preview(self.root, self.plan['id'], True, source_review, cursor, 16)
            preview.extend(page['records']);cursor = page['next_cursor']
            if cursor is None: break
        self.assertEqual(records[:256], preview)
        with sampling.indexes._connect(sessions._folder(self.root, state['id']) / 'session.sqlite3', True) as db:
            metadata = [row[0] for row in db.execute('SELECT value FROM state UNION ALL SELECT value FROM receipts')]
        self.assertNotIn('full-left original record', ''.join(metadata))
        for packet in packets:
            self.assertTrue(all('text' not in reference for reference in packet['receipt']['references']))

    def test_concurrent_declaration_update_rolls_back_batch(self):
        state = self.begin();commit = sessions._commit

        def changed(*args):
            commit(*args)
            self.fixture.declare(self.fixture.sources[0], 'user_created', 'Concurrent declaration update')

        with patch.object(sessions, '_commit', side_effect=changed):
            with self.assertRaises(ValueError): self.step(state)
        database = sessions._folder(self.root, state['id']) / 'session.sqlite3'
        with sampling.indexes._connect(database, True) as db:
            self.assertEqual(sessions._state(db), state)
            self.assertEqual(db.execute('SELECT MAX(sequence) FROM receipts').fetchone()[0], None)

    def test_completed_receipt_database_tamper_rejects(self):
        state, _ = self.complete(self.begin())
        database = sessions._folder(self.root, state['id']) / 'session.sqlite3'
        with database.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): sessions.read(self.root, state['id'])

    def test_app_review_begin_step_and_replay_routes(self):
        def post(path, data):
            raw = json.dumps(data).encode()
            handler = Mock(path=path, headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            return handler.respond.call_args.args[0]
        base = '/decoder-stream-mixtures/' + self.plan['id']
        reviewed = post(base + '/session-review', {'confirmed': True, 'reviewed': self.plan})
        state = post(base + '/sampling-sessions', {'confirmed': True, 'reviewed': reviewed})
        route = '/decoder-stream-mixture-sessions/' + state['id']
        packet = post(route + '/step', {'confirmed': True, 'request_id': 'a' * 32, 'limit': 8})
        self.assertEqual(post(route + '/batch', {'confirmed': True, 'sequence': 1}), packet)
        handler = Mock(path=route);handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_GET(handler)
        self.assertEqual(handler.respond.call_args.args[0]['position'], 8)
