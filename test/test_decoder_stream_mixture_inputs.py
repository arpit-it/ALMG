import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import string
from tempfile import TemporaryDirectory
import unicodedata
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_permissions as permissions
from backend import decoder_stream_token_stats as stats, decoder_stream_tokenizers as tokenizers
from backend import decoder_stream_mixtures as mixtures, decoder_stream_mixture_sessions as sessions, decoder_stream_mixture_inputs as inputs, studio
from backend.run_manifest import digest, file_digest


class MixtureInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.letters = [letter for letter in string.ascii_letters if int(digest(letter)[:8], 16) % 100 < 80]
        self.left = self.source('left', [self.letters[0], self.train('cafe\u0301 東京 🙂 ' * 8), self.train('left long document spanning several windows ')])
        self.right = self.source('right', [self.letters[1], self.train('世界 bonjour 🙂 ' * 9), self.train('right independent document spanning several windows ')])
        self.state, self.packet = self.session(self.left, self.right)
        self.tokenizer = self.fit(self.left)
        self.reviewed = self.review(self.state, self.packet, self.tokenizer)

    def train(self, prefix):
        for i in range(1000):
            raw = prefix + str(i)
            if int(digest(' '.join(unicodedata.normalize('NFC', raw).split()))[:8], 16) % 100 < 80: return raw
        raise AssertionError('No train fixture')

    def source(self, name, rows):
        raw = ('\n'.join(rows) + '\n').encode()
        source = streams.create(self.root, name + '.txt', len(raw), hashlib.sha256(raw).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(raw).decode(), True);streams.seal(self.root, source['id'], True)
        record = indexes.begin(self.root, source['id'], True);record = indexes.step(self.root, record['id'], True)
        permissions.declare(self.root, record['id'], True, permissions.review(self.root, record['id']), 'user_created', 'Generated fixture')
        return record

    def session(self, left, right):
        plan = mixtures.save(self.root, True, mixtures.review(self.root, True, [{'index_id': left['id'], 'weight': 1}, {'index_id': right['id'], 'weight': 3}]))
        state = sessions.begin(self.root, plan['id'], True, sessions.review(self.root, plan['id'], True, plan))
        packet = sessions.step(self.root, state['id'], True, 'a' * 32, 16)
        return sessions.read(self.root, state['id']), packet

    def fit(self, index):
        report = stats.begin(self.root, index['id'], True)
        while report['status'] != 'complete': report = stats.step(self.root, report['id'], True)
        return tokenizers.prepare(self.root, report['id'], True, report)

    def review(self, state, packet, tokenizer):
        return inputs.review(self.root, state['id'], True, 1, packet['receipt'], tokenizer['id'], tokenizer)

    def test_every_causal_transition_exactly_once_without_cross_document_targets(self):
        expected = [(record['position'], offset, a, b) for record in self.packet['records']
                    for offset, (a, b) in enumerate(zip(record['text'].encode(), record['text'].encode()[1:]))]
        totals = []
        for size in (1, 4, 16):
            cursor = None;actual = [];windows = 0
            while True:
                page = inputs.batch(self.root, self.state['id'], True, self.reviewed, cursor, size)
                self.assertLessEqual(page['rows'], size)
                for x, y, mask, length, provenance in zip(page['inputs'], page['targets'], page['loss_mask'], page['sequence_lengths'], page['provenance']):
                    self.assertEqual((len(x), len(y), len(mask)), (16, 16, 16))
                    self.assertEqual(mask, [1] * length + [0] * (16 - length))
                    self.assertEqual(x[length:], [0] * (16 - length));self.assertEqual(y[length:], [0] * (16 - length))
                    actual.extend((provenance['position'], provenance['token_offset'] + j, x[j], y[j]) for j in range(length))
                    self.assertNotIn('text', provenance);windows += 1
                cursor = page['next_cursor']
                if cursor is None: break
            self.assertEqual(actual, expected);self.assertEqual(windows, self.reviewed['total_windows']);totals.append(actual)
        self.assertEqual(self.reviewed['total_target_tokens'], len(expected))
        self.assertEqual(len(self.reviewed['records_without_targets']), 2)
        self.assertTrue(any(a > 127 or b > 127 for _, _, a, b in expected))
        self.assertEqual(totals[0], totals[2])

    def test_codec_provenance_is_not_misrepresented_as_joint_training(self):
        self.assertEqual(self.reviewed['tokenizer'], self.tokenizer)
        self.assertEqual(self.reviewed['vocabulary_size'], 256)
        self.assertFalse(self.reviewed['method']['joint_mixture_tokenizer_fit_performed'])
        self.assertFalse(self.reviewed['method']['padding_is_special_token'])
        for flag in sessions.FLAGS: self.assertIs(self.reviewed[flag], False)
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        inputs.batch(self.root, self.state['id'], True, self.reviewed)
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_consent_sizes_and_cursors_reject(self):
        with patch.object(inputs, '_load') as inspected:
            with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], False, self.reviewed)
            for size in (True, 0, 17):
                with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], True, self.reviewed, batch_size=size)
            inspected.assert_not_called()
        with self.assertRaises(ValueError): inputs.review(self.root, self.state['id'], False, 1, self.packet['receipt'], self.tokenizer['id'], self.tokenizer)
        first = inputs.batch(self.root, self.state['id'], True, self.reviewed, batch_size=1);cursor = first['next_cursor']
        for change in ({'revision': 'changed'}, {'record_index': True}, {'token_offset': 1}, {'token_offset': 4096}):
            with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], True, self.reviewed, {**cursor, **change})
        no_target = self.reviewed['document_token_counts'].index(1)
        with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], True, self.reviewed, {'revision': self.reviewed['revision'], 'record_index': no_target, 'token_offset': 0})

    def test_receipt_tokenizer_and_source_bindings_reject_stale_inputs(self):
        changed = deepcopy(self.packet['receipt']);changed['payload_sha256'] = 'f' * 64
        with self.assertRaises(ValueError): inputs.review(self.root, self.state['id'], True, 1, changed, self.tokenizer['id'], self.tokenizer)
        outside = self.fit(self.source('outsider', [self.train('outside local source ')]))
        with self.assertRaisesRegex(ValueError, 'current source in this mixture'): self.review(self.state, self.packet, outside)
        artifact = tokenizers._folder(self.root, self.tokenizer['id']) / 'tokenizer.json'
        with artifact.open('ab') as stream: stream.write(b' ')
        with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], True, self.reviewed)

    def test_over_limit_record_rejects_without_truncation_or_sampler_advance(self):
        large = self.source('large', [self.train('word ' * 1025)])
        state, packet = self.session(self.left, large)
        database = sessions._folder(self.root, state['id']) / 'session.sqlite3';before = file_digest(database)
        with self.assertRaisesRegex(ValueError, '4096 encoded bytes'): self.review(state, packet, self.tokenizer)
        self.assertEqual(file_digest(database), before)
        self.assertEqual(sessions.batch(self.root, state['id'], True, 1), packet)

    def test_all_single_byte_records_return_no_artificial_training_row(self):
        left = self.source('short-left', self.letters[2:5]);right = self.source('short-right', self.letters[5:8])
        state, packet = self.session(left, right);tokenizer = self.fit(left)
        reviewed = self.review(state, packet, tokenizer)
        page = inputs.batch(self.root, state['id'], True, reviewed)
        self.assertEqual(reviewed['total_target_tokens'], 0);self.assertEqual(reviewed['total_windows'], 0)
        self.assertEqual(len(reviewed['records_without_targets']), 6)
        self.assertEqual(page['rows'], 0);self.assertIsNone(page['next_cursor'])

    def test_changed_declaration_rejects_existing_review(self):
        source = self.left
        permissions.declare(self.root, source['id'], True, permissions.review(self.root, source['id']), 'needs_review', 'Updated fixture')
        with self.assertRaises(ValueError): inputs.batch(self.root, self.state['id'], True, self.reviewed)

    def test_unavailable_artifact_and_sqlite_failures_return_explicit_rejection(self):
        path = tokenizers._folder(self.root, self.tokenizer['id']) / 'tokenizer.json'
        original = path.read_bytes();path.unlink()
        try:
            with self.assertRaisesRegex(ValueError, 'unavailable; no valid inputs'):
                inputs.batch(self.root, self.state['id'], True, self.reviewed)
        finally:
            path.write_bytes(original)
        with patch.object(inputs, '_load', side_effect=inputs.sqlite3.OperationalError('Fixture unavailable')):
            with self.assertRaisesRegex(ValueError, 'unavailable; no valid inputs'):
                self.review(self.state, self.packet, self.tokenizer)

    def test_app_review_and_input_batch_routes(self):
        values = {'confirmed': True, 'sequence': 1, 'reviewed_receipt': self.packet['receipt'], 'tokenizer_id': self.tokenizer['id'], 'reviewed_tokenizer': self.tokenizer}
        for action in ('input-review', 'input-batch'):
            if action == 'input-batch': values = {'confirmed': True, 'reviewed': self.reviewed, 'batch_size': 2}
            raw = json.dumps(values).encode()
            handler = Mock(path='/decoder-stream-mixture-sessions/' + self.state['id'] + '/' + action,
                           headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            result = handler.respond.call_args.args[0];self.assertNotIn('error', result)
            if action == 'input-batch': self.assertEqual(result['rows'], 2)
