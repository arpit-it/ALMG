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
