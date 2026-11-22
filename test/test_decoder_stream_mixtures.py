import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_streams as streams, decoder_stream_indexes as indexes
from backend import decoder_stream_jsonl as jsonl, decoder_stream_mixtures as mixtures, studio
from backend.run_manifest import digest


class StreamMixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.source('orchard', False)
        self.second = self.source('astronomy', True)
        self.sources = [{'index_id': self.first['id'], 'weight': 1},
                        {'index_id': self.second['id'], 'weight': 3}]

    def source(self, prefix, as_jsonl=False):
        rows = [f'{prefix} independent local document number {i}' for i in range(100)]
        data = ('\n'.join(json.dumps({'text': row}) if as_jsonl else row for row in rows) + '\n').encode()
        source = streams.create(self.root, prefix + ('.jsonl' if as_jsonl else '.txt'), len(data), hashlib.sha256(data).hexdigest(), True)
        streams.append(self.root, source['id'], 0, base64.b64encode(data).decode(), True)
        streams.seal(self.root, source['id'], True)
        worker = jsonl if as_jsonl else indexes
        record = worker.begin(self.root, source['id'], True)
        return worker.step(self.root, record['id'], True)

    def test_exact_weight_shares_bound_counts_provenance_and_no_source_mutation(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for split in ('train', 'validation', 'test'):
            review = mixtures.review(self.root, True, self.sources, split)
            self.assertEqual(review, mixtures.review(self.root, True, list(reversed(self.sources)), split))
            for value in review['sources']:
                index = self.first if value['index_id'] == self.first['id'] else self.second
                self.assertEqual(value['index_revision'], index['revision'])
                self.assertEqual(value['index_file_sha256'], index['files']['records.sqlite3'])
                self.assertEqual(value['available_records'], index['split_counts'][split])
                self.assertEqual(value['source_sha256'], index['source_sha256'])
                self.assertEqual(value['target_record_share'], {'numerator': value['weight'], 'denominator': 4})
            self.assertFalse(review['training_approved'])
            self.assertFalse(review['method']['sampling_executed'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_explicit_consent_and_invalid_selections_reject_before_publishing(self):
        with self.assertRaises(ValueError): mixtures.review(self.root, False, self.sources)
        for sources in (None, [], self.sources[:1], self.sources * 5,
                        [self.sources[0], self.sources[0]],
                        [dict(self.sources[0], index_id='../unsafe'), self.sources[1]]):
            with self.assertRaises(ValueError): mixtures.review(self.root, True, sources)
        for weight in (True, 0, -1, 1001, 1.5, '3', None):
            with self.assertRaises(ValueError):
                mixtures.review(self.root, True, [dict(self.sources[0], weight=weight), self.sources[1]])
        with self.assertRaises(ValueError): mixtures.review(self.root, True, self.sources, 'all')
        with self.assertRaises(ValueError): mixtures.save(self.root, False, mixtures.review(self.root, True, self.sources))
        self.assertFalse((self.root / 'decoder-stream-mixtures').exists())

    def test_same_original_and_incomplete_or_empty_sources_reject(self):
        other = indexes.begin(self.root, self.first['source_id'], True)
        incomplete = [self.sources[0], {'index_id': other['id'], 'weight': 2}]
        with self.assertRaisesRegex(ValueError, 'Complete every'): mixtures.review(self.root, True, incomplete)
        indexes.step(self.root, other['id'], True)
        with self.assertRaisesRegex(ValueError, 'same original'): mixtures.review(self.root, True, incomplete)
        changed = deepcopy(self.second)
        changed['split_counts']['test'] = 0
        original = indexes.read
        with patch.object(indexes, 'read', side_effect=lambda root, identifier: changed if identifier == changed['id'] else original(root, identifier)):
            with self.assertRaisesRegex(ValueError, 'selected split'): mixtures.review(self.root, True, self.sources, 'test')

    def test_save_reopen_restart_and_old_producer_provenance(self):
        review = mixtures.review(self.root, True, self.sources)
        record = mixtures.save(self.root, True, review)
        path = mixtures._folder(self.root, record['id']) / 'manifest.json'
        before = path.read_bytes()
        self.assertEqual(mixtures.read(self.root, record['id']), record)
        # Loading has no process-local registry and preserves a prior producer digest.
        with patch.object(mixtures, 'file_digest', return_value='new-producer'):
            self.assertEqual(mixtures.read(self.root, record['id']), record)
            with self.assertRaisesRegex(ValueError, 'changed'): mixtures.save(self.root, True, review)
        self.assertEqual(path.read_bytes(), before)

    def test_stale_weight_or_source_review_and_failed_publication_preserve_sources(self):
        review = mixtures.review(self.root, True, self.sources)
        for changed in (dict(review, split='validation'), deepcopy(review)):
            if changed['split'] == 'train': changed['sources'][0]['weight'] += 1
            with self.assertRaisesRegex(ValueError, 'changed'): mixtures.save(self.root, True, changed)
        with patch.object(mixtures, 'review', side_effect=[review, ValueError('Source changed during save')]):
            with self.assertRaises(ValueError): mixtures.save(self.root, True, review)
        self.assertEqual(list((self.root / 'decoder-stream-mixtures').iterdir()), [])
        self.assertEqual(indexes.read(self.root, self.first['id']), self.first)

    def test_manifest_and_source_tampering_rejected_without_rewriting_plan(self):
        record = mixtures.save(self.root, True, mixtures.review(self.root, True, self.sources))
        path = mixtures._folder(self.root, record['id']) / 'manifest.json'
        original = path.read_bytes()
        record['review']['sources'][0]['target_record_share']['numerator'] = 99
        record['review']['revision'] = digest({k: v for k, v in record['review'].items() if k != 'revision'})
        record['revision'] = digest({k: v for k, v in record.items() if k != 'revision'})
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'bindings or calculated shares'): mixtures.read(self.root, record['id'])
        path.write_bytes(original)
        db = indexes._folder(self.root, self.first['id']) / 'records.sqlite3'
        with db.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): mixtures.read(self.root, record['id'])
        self.assertEqual(path.read_bytes(), original)

    def test_routes_dispatch_review_save_and_reopen(self):
        from io import BytesIO
        reviewed = mixtures.review(self.root, True, self.sources)
        for path, data in (('/decoder-stream-mixtures/review', {'confirmed': True, 'sources': self.sources}),
                           ('/decoder-stream-mixtures', {'confirmed': True, 'reviewed': reviewed})):
            raw = json.dumps(data).encode()
            handler = Mock(path=path, headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
            result = handler.respond.call_args.args[0]
            self.assertNotIn('error', result)
        handler = Mock(path='/decoder-stream-mixtures/' + result['id'])
        handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_GET(handler)
        self.assertEqual(handler.respond.call_args.args[0], result)
