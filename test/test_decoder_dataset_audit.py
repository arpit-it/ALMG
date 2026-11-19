import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_datasets as datasets


class DatasetAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        words = [f'w{i}' for i in range(40)]
        self.manifest = datasets.prepare(self.root, [
            {'name': f'near-{i}.txt', 'text': ' '.join(words + [f'unique{i}'])}
            for i in range(6)], True)
        self.dataset_id = self.manifest['id']

    def test_overlap_provenance_and_immutable_repeat(self):
        folder = self.root / 'decoder-datasets' / self.dataset_id
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        report = datasets.audit(self.root, self.dataset_id, True)
        self.assertEqual((report['near_duplicate_pairs'], report['cross_split_pairs']), (15, 9))
        for finding in report['findings']:
            self.assertEqual(len(finding['records']), 2)
            for record in finding['records']:
                source = next(s for s in self.manifest['sources'] if s['name'] == record['name'])
                self.assertEqual(record['source_sha256'], source['source_sha256'])
                self.assertEqual(record['split'], source['split'])
            self.assertEqual(finding['cross_split'], len({r['split'] for r in finding['records']}) > 1)
        self.assertEqual(datasets.audit(self.root, self.dataset_id, True), report)
        self.assertEqual(datasets.list_audits(self.root, self.dataset_id), [report])
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'decoder-datasets', 'decoder-dataset-audits'})
        self.assertEqual(len(list((self.root / 'decoder-dataset-audits' / self.dataset_id).iterdir())), 1)

    def test_unrelated_and_short_documents(self):
        manifest = datasets.prepare(self.root, [
            {'name': 'short', 'text': 'small sample'},
            {'name': 'a', 'text': ' '.join(f'a{i}' for i in range(30))},
            {'name': 'b', 'text': ' '.join(f'b{i}' for i in range(30))}], True)
        report = datasets.audit(self.root, manifest['id'], True)
        self.assertEqual(report['near_duplicate_pairs'], 0)
        self.assertEqual([f['kind'] for f in report['findings']], ['short_document'])
        self.assertEqual(report['findings'][0]['record']['name'], 'short')

    def test_privacy_locations_preserve_provenance_without_copying_contact_values(self):
        documents = [
            {'name': 'contacts.txt', 'text': '\ufeffcafé  contact alice@example.test or +44 20 7946 0958 today'},
            {'name': 'domestic.txt', 'text': 'Call (415) 555-0123 for this fictional local fixture.'},
            {'name': 'control.txt', 'text': 'Date 2026-11-19; version 1.2.3; identifier 1234567; word at example dot test.'},
        ]
        manifest = datasets.prepare(self.root, documents, True, 'utf8_bytes')
        folder = self.root / 'decoder-datasets' / manifest['id']
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        report = datasets.audit(self.root, manifest['id'], True)
        self.assertEqual(report['audit_version'], 2)
        self.assertEqual(report['privacy_matches'], 3)
        findings = [f for f in report['findings'] if f['kind'] == 'potential_personal_information']
        self.assertEqual(sorted(f['category'] for f in findings), ['email_address', 'phone_number', 'phone_number'])
        rows = {row['name']: row for row in map(json.loads, (folder / 'documents.jsonl').read_text().splitlines())}
        detected = []
        for finding in findings:
            row = rows[finding['record']['name']]
            self.assertEqual(finding['record']['source_sha256'], row['source_sha256'])
            self.assertEqual(finding['record']['split'], row['split'])
            detected.append(row['text'][finding['normalized_character_start']:finding['normalized_character_end']])
        self.assertEqual(set(detected), {'alice@example.test', '+44 20 7946 0958', '(415) 555-0123'})
        serialized = json.dumps(report)
        for value in detected:
            self.assertNotIn(value, serialized)
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(datasets.audit(self.root, manifest['id'], True), report)
        self.assertEqual(datasets.list_audits(self.root, manifest['id']), [report])

    def test_legacy_saved_audit_remains_readable_alongside_privacy_revision(self):
        current = datasets.audit(self.root, self.dataset_id, True)
        legacy = dict(current, audit_version=1)
        for key in ('revision', 'privacy_matches', 'privacy_method'):
            legacy.pop(key)
        legacy['revision'] = datasets.digest(legacy)
        path = self.root / 'decoder-dataset-audits' / self.dataset_id / (legacy['revision'] + '.json')
        path.write_text(json.dumps(legacy))
        saved = datasets.list_audits(self.root, self.dataset_id)
        self.assertEqual({row['audit_version'] for row in saved}, {1, 2})
        self.assertEqual(json.loads(path.read_text()), legacy)

    def test_consent_and_corrupt_dataset_do_not_publish(self):
        for consent in (False, None, 1):
            with self.assertRaises(ValueError):
                datasets.audit(self.root, self.dataset_id, consent)
        (self.root / 'decoder-datasets' / self.dataset_id / 'documents.jsonl').write_text('{}')
        with self.assertRaises(ValueError):
            datasets.audit(self.root, self.dataset_id, True)
        self.assertFalse((self.root / 'decoder-dataset-audits').exists())

    def test_tampered_audit_is_not_reused(self):
        report = datasets.audit(self.root, self.dataset_id, True)
        path = self.root / 'decoder-dataset-audits' / self.dataset_id / (report['revision'] + '.json')
        report['cross_split_pairs'] = 0
        path.write_text(json.dumps(report))
        self.assertEqual(datasets.list_audits(self.root, self.dataset_id), [])
        with self.assertRaises(ValueError):
            datasets.audit(self.root, self.dataset_id, True)


if __name__ == '__main__':
    unittest.main()
