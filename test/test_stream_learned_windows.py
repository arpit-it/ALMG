import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_overlap as overlap
from backend import decoder_stream_iterative_bpe as fits, decoder_stream_fitted_tokenizer_evaluations as scans, decoder_stream_learned_windows as windows


def finish(worker, root, record):
    while record['status'] != 'complete': record = worker.step(root, record['id'], True)
    return record


def pipeline(root, lines):
    raw = ('\n'.join(lines) + '\n').encode()
    source = streams.create(root, 'learned.txt', len(raw), hashlib.sha256(raw).hexdigest(), True)
    for offset in range(0, len(raw), 65536): streams.append(root, source['id'], offset, base64.b64encode(raw[offset:offset+65536]).decode(), True)
    streams.seal(root, source['id'], True)
    index = finish(indexes, root, indexes.begin(root, source['id'], True))
    fit = finish(fits, root, fits.begin(root, index['id'], True, fits.review(root, index['id'], 260)))
    comparison = finish(scans, root, scans.begin(root, fit['id'], True, fit, 'iterative'))
    evidence = finish(overlap, root, overlap.begin(root, index['id'], True))
    return comparison, evidence


class LearnedWindowsTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        self.comparison, self.overlap = pipeline(self.root, [f'record{i} banana café 世界' for i in range(41)] + ['long ' + 'banana ' * 700])
        self.review = windows.review(self.root, self.comparison['id'], self.overlap['id'])

    def begin(self): return windows.begin(self.root, self.comparison['id'], self.overlap['id'], True, self.review)

    def test_restart_exact_learned_tokens_provenance_masks_and_split_cursors(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        record = self.begin()
        with patch.object(windows, 'MAX_BATCH_RECORDS', 3): record = windows.step(self.root, record['id'], True)
        self.assertEqual(record['processed_records'], 3)
        importlib.reload(windows); self.assertEqual(windows.read(self.root, record['id']), record)
        record = finish(windows, self.root, record)
        _, _, codec, _ = scans._binding(self.root, self.comparison['fit_id'], 'iterative', True)
        with indexes._connect(indexes._folder(self.root, record['index_id'])/'records.sqlite3', True) as db:
            source = {row[0]: row[1:] for row in db.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents')}
        with indexes._connect(windows._folder(self.root, record['id'])/'windows.sqlite3', True) as db:
            rows = db.execute('SELECT group_sha256,token_offset,split,tokens FROM windows').fetchall()
            self.assertTrue(any(max(json.loads(row[3])) >= 256 for row in rows))
            for group, offset, split, encoded in rows:
                self.assertEqual(json.loads(encoded), codec.encode(source[group][0])[offset:offset+17]); self.assertEqual(split, source[group][1])
                self.assertEqual(offset % 16, 0)
        self.assertEqual(record['target_tokens'], sum(len(codec.encode(value[0]))-1 for value in source.values()))
        padded = False
        for split in ('train', 'validation', 'test'):
            cursor = None; seen = set(); targets = 0
            while True:
                batch = windows.read_batch(self.root, record['id'], True, record, cursor, split, 16)
                self.assertFalse(batch['training_approved']); self.assertFalse(batch['method']['model_execution_enabled'])
                for inputs, output, mask, length, provenance in zip(batch['inputs'], batch['targets'], batch['loss_mask'], batch['sequence_lengths'], batch['provenance']):
                    key = (provenance['group'], provenance['token_offset']); self.assertNotIn(key, seen); seen.add(key)
                    doc = source[key[0]]; ids = codec.encode(doc[0])[key[1]:key[1]+17]
                    self.assertEqual(inputs[:length], ids[:-1]); self.assertEqual(output[:length], ids[1:])
                    self.assertEqual(mask, [1]*length+[0]*(16-length)); self.assertEqual(inputs[length:], [0]*(16-length)); self.assertEqual(output[length:], [0]*(16-length))
                    self.assertEqual(provenance['first_line'], doc[2]); self.assertEqual(provenance['raw_line_sha256'], doc[4]); self.assertEqual(provenance['split'], split)
                    padded |= length < 16
                targets += batch['real_target_tokens']; cursor = batch['next_cursor']
                if cursor is None: break
            self.assertEqual(targets, sum(len(codec.encode(value[0]))-1 for value in source.values() if value[1] == split))
        self.assertTrue(padded); self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
        page = windows.record_page(self.root, record['id'], True)
        with self.assertRaises(ValueError): windows.record_page(self.root, record['id'], True, page['next_cursor'], 'test')
        with self.assertRaises(ValueError): windows.read_batch(self.root, record['id'], True, {})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_consent_stale_review_and_contamination_reject_without_creating_windows(self):
        for confirmed, reviewed in [(False, self.review), (True, {})]:
            with self.assertRaises(ValueError): windows.begin(self.root, self.comparison['id'], self.overlap['id'], confirmed, reviewed)
        comparison, evidence = pipeline(self.root, [' '.join([f'word{j}' for j in range(40)] + [f'tail{i}']) for i in range(35)])
        self.assertGreater(evidence['cross_split_pairs'], 0)
        with self.assertRaisesRegex(ValueError, 'Cross-split'): windows.review(self.root, comparison['id'], evidence['id'])
        self.assertFalse((self.root/'decoder-stream-learned-windows').exists())

    def test_transaction_rollback_source_guard_and_publication_recovery(self):
        record = self.begin(); original = fits.StreamByteBPE.encode; calls = 0
        def interrupted(codec, text):
            nonlocal calls
            calls += 1
            if calls == 4: raise RuntimeError('interrupted fixture')
            return original(codec, text)
        with patch.object(fits.StreamByteBPE, 'encode', interrupted):
            with self.assertRaises(RuntimeError): windows.step(self.root, record['id'], True)
        self.assertEqual(windows.read(self.root, record['id']), record)
        with indexes._connect(windows._folder(self.root, record['id'])/'windows.sqlite3', True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM windows').fetchone()[0], 0)
        with patch.object(windows, '_publish', side_effect=OSError('publication interrupted')):
            with self.assertRaises(OSError): windows.step(self.root, record['id'], True)
        pending = windows.read(self.root, record['id']); self.assertEqual(pending['status'], 'awaiting_publication')
        complete = windows.step(self.root, record['id'], True); self.assertEqual(complete['processed_records'], pending['processed_records'])
        self.assertEqual(windows.step(self.root, record['id'], True), complete)
        source = streams.folder(self.root, complete['source_id'])/'source.bin'; source.write_bytes(source.read_bytes()+b'x')
        with self.assertRaises(ValueError): windows.read_batch(self.root, complete['id'], True, complete)

    def test_single_learned_token_cannot_silently_drop_a_record(self):
        record = self.begin()
        with patch.object(fits.StreamByteBPE, 'encode', return_value=[256]):
            with self.assertRaisesRegex(ValueError, 'at least two'): windows.step(self.root, record['id'], True)
        self.assertEqual(windows.read(self.root, record['id']), record)

    def test_one_merge_fit_and_incomplete_comparison_guards(self):
        from backend import decoder_stream_bpe as one
        index_id = self.comparison['index_id']
        fit = finish(one, self.root, one.begin(self.root, index_id, True, one.review(self.root, index_id)))
        comparison = scans.begin(self.root, fit['id'], True, fit, 'one_merge')
        with self.assertRaisesRegex(ValueError, 'Complete a lossless'): windows.review(self.root, comparison['id'], self.overlap['id'])
        comparison = finish(scans, self.root, comparison)
        reviewed = windows.review(self.root, comparison['id'], self.overlap['id'])
        record = finish(windows, self.root, windows.begin(self.root, comparison['id'], self.overlap['id'], True, reviewed))
        self.assertEqual(record['vocabulary_size'], 257)
        self.assertEqual(record['encoded_tokens'], sum(value['encoded_tokens'] for value in comparison['splits'].values()))

    def test_permission_change_and_mid_batch_rewrite_preserve_prior_progress(self):
        from backend import decoder_stream_permissions as permissions
        record = self.begin()
        with patch.object(windows, 'MAX_BATCH_RECORDS', 3): record = windows.step(self.root, record['id'], True)
        binding = windows._sources; calls = 0
        path = fits._folder(self.root, self.comparison['fit_id'])/'artifacts'/'tokenizer.json'
        def rewritten(*args):
            nonlocal calls
            calls += 1
            if calls == 2: path.write_bytes(path.read_bytes())
            return binding(*args)
        with patch.object(windows, '_sources', side_effect=rewritten):
            with self.assertRaisesRegex(ValueError, 'changed during'): windows.step(self.root, record['id'], True)
        self.assertEqual(windows.read(self.root, record['id']), record)
        old = permissions.review(self.root, record['index_id'])
        permissions.declare(self.root, record['index_id'], True, old, 'user_created', 'QA')
        with self.assertRaisesRegex(ValueError, 'permissions changed'): windows.step(self.root, record['id'], True)
        self.assertEqual(windows.read(self.root, record['id']), record)
