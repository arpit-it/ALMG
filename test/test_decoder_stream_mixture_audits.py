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
from backend import decoder_stream_mixtures as mixtures, decoder_stream_mixture_overlap as overlap
from backend import decoder_stream_mixture_audits as audits, studio
from backend.run_manifest import digest


class MixtureAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        sources = []
        for name in ('orchard', 'astronomy'):
            data = ('\n'.join([f'{name} local record {i}' for i in range(100)] + ['common local record']) + '\n').encode()
            source = streams.create(self.root, name + '.txt', len(data), hashlib.sha256(data).hexdigest(), True)
            streams.append(self.root, source['id'], 0, base64.b64encode(data).decode(), True)
            streams.seal(self.root, source['id'], True)
            index = indexes.begin(self.root, source['id'], True)
            index = indexes.step(self.root, index['id'], True)
            sources.append({'index_id': index['id'], 'weight': 1})
        self.plan = mixtures.save(self.root, True, mixtures.review(self.root, True, sources))
        self.report = overlap.review(self.root, self.plan['id'], True, self.plan)

    def save(self, report=None):
        return audits.save(self.root, self.plan['id'], True, self.plan, self.report if report is None else report)

    def read(self, record):
        return audits.read(self.root, self.plan['id'], record['id'])

    def test_immutable_snapshots_and_ordered_history_preserve_sources(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(audits.history(self.root, self.plan['id'])['records'], [])
        self.assertFalse(audits._folder(self.root, self.plan['id']).exists())
        first, second = self.save(), self.save()
        self.assertNotEqual(first['id'], second['id'])
        for record in (first, second):
            self.assertEqual(record['report'], self.report)
            self.assertFalse(record['training_approved'])
            self.assertEqual(self.read(record), record)
        history = audits.history(self.root, self.plan['id'])
        self.assertTrue(history['history_complete'])
        self.assertEqual([record['id'] for record in history['records']], [first['id'], second['id']])
        self.assertEqual(history['records'][0]['exact_overlap_record_pairs'], 1)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertNotIn('common local record', json.dumps(first))

    def test_consent_and_stale_report_reject_without_publication(self):
        with self.assertRaises(ValueError): audits.save(self.root, self.plan['id'], False, self.plan, self.report)
        changed = deepcopy(self.report)
        changed['exact_overlap_record_pairs'] += 1
        for value in (None, changed):
            with self.assertRaisesRegex(ValueError, 'report changed'):
                audits.save(self.root, self.plan['id'], True, self.plan, value)
        stale_plan = deepcopy(self.plan)
        stale_plan['review']['sources'][0]['weight'] += 1
        with self.assertRaises(ValueError): audits.save(self.root, self.plan['id'], True, stale_plan, self.report)
        self.assertFalse(audits._folder(self.root, self.plan['id']).exists())

    def test_interrupted_publication_preserves_prior_evidence_and_cleans_staging(self):
        first = self.save()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(overlap, 'review', side_effect=[self.report, ValueError('Fixture source changed')]):
            with self.assertRaises(ValueError): self.save()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual([path.name for path in audits._folder(self.root, self.plan['id']).iterdir()], [first['id']])
        self.assertEqual(self.read(first), first)

    def test_corrupt_report_cannot_hide_in_a_partial_history(self):
        first, second = self.save(), self.save()
        path = audits._folder(self.root, self.plan['id'], first['id']) / 'manifest.json'
        original = path.read_bytes()
        changed = deepcopy(first)
        changed['report']['exact_overlap_record_pairs'] += 1
        changed['report']['revision'] = digest({k: v for k, v in changed['report'].items() if k != 'revision'})
        changed['revision'] = digest({k: v for k, v in changed.items() if k != 'revision'})
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError): self.read(first)
        with self.assertRaises(ValueError): audits.history(self.root, self.plan['id'])
        with self.assertRaises(ValueError): self.save()
        self.assertEqual(self.read(second), second)
        path.write_bytes(original)
        self.assertEqual(audits.history(self.root, self.plan['id'])['record_count'], 2)

    def test_prior_producer_results_remain_readable_without_rewriting(self):
        record = self.save()
        path = audits._folder(self.root, self.plan['id'], record['id']) / 'manifest.json'
        before = path.read_bytes()
        original = overlap.review

        def upgraded(*args, **kwargs):
            result = original(*args, **kwargs)
            result['implementation_sha256'] = 'f' * 64
            result['revision'] = digest({k: v for k, v in result.items() if k != 'revision'})
            return result

        with patch.object(overlap, 'review', side_effect=upgraded):
            self.assertEqual(self.read(record), record)
            self.assertEqual(audits.history(self.root, self.plan['id'])['records'][0]['report_revision'], self.report['revision'])
            with self.assertRaisesRegex(ValueError, 'report changed'): self.save()
        self.assertEqual(path.read_bytes(), before)

    def test_history_capacity_rejects_new_writes_without_deleting_evidence(self):
        with patch.object(audits, 'MAX_RECORDS', 2):
            first, second = self.save(), self.save()
            before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'history is full'): self.save()
            self.assertEqual(audits.history(self.root, self.plan['id'])['record_count'], 2)
            self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
            self.assertEqual(self.read(first), first)
            self.assertEqual(self.read(second), second)

    def test_manifest_bound_and_unknown_history_entries_fail_closed(self):
        record = self.save()
        path = audits._folder(self.root, self.plan['id'], record['id']) / 'manifest.json'
        original = path.read_bytes()
        path.write_bytes(b' ' * (audits.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'size limit'): self.read(record)
        path.write_bytes(original)
        unexpected = path.parent.parent / 'unexpected.json'
        unexpected.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Unexpected'): audits.history(self.root, self.plan['id'])
        unexpected.unlink()
        for identifier in ('../unsafe', None):
            with self.assertRaises(ValueError): audits.read(self.root, self.plan['id'], identifier)

    def test_changed_source_rejects_without_rewriting_audit(self):
        record = self.save()
        path = audits._folder(self.root, self.plan['id'], record['id']) / 'manifest.json'
        original = path.read_bytes()
        database = indexes._folder(self.root, self.plan['review']['sources'][0]['index_id']) / 'records.sqlite3'
        with database.open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(ValueError): self.read(record)
        with self.assertRaises(ValueError): audits.history(self.root, self.plan['id'])
        self.assertEqual(path.read_bytes(), original)

    def test_app_save_history_and_read_routes(self):
        route = '/decoder-stream-mixtures/' + self.plan['id'] + '/exact-overlap-audits'
        raw = json.dumps({'confirmed': True, 'reviewed': self.plan, 'reviewed_report': self.report}).encode()
        handler = Mock(path=route, headers={'Content-Length': str(len(raw))}, rfile=BytesIO(raw))
        handler.authorized.return_value = True
        with patch.object(studio, 'ROOT', self.root): studio.Handler.do_POST(handler)
        record = handler.respond.call_args.args[0]
        for path in (route, route + '/' + record['id']):
            handler = Mock(path=path)
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', self.root): studio.Handler.do_GET(handler)
            result = handler.respond.call_args.args[0]
            if path == route: self.assertEqual(result['record_count'], 1)
            else: self.assertEqual(result, record)
