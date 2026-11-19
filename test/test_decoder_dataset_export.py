import base64
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from backend import decoder_datasets as datasets


class DatasetExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parent = datasets.prepare(self.root, [
            {'name': 'contact.txt', 'text': 'Contact alice@example.test for a local fixture.'},
            {'name': 'phone.txt', 'text': 'Call +44 20 7946 0958 for another fixture.'},
            {'name': 'control.txt', 'text': 'Independent local control with café text.'},
        ], True, 'utf8_bytes')
        audit = datasets.quality_report(self.root, self.parent['id'])
        self.child = datasets.redact(self.root, self.parent['id'], True, audit['revision'])
        self.dataset_id = self.child['id']

    def test_export_preserves_exact_files_lineage_and_reproducibility(self):
        folder = self.root / 'decoder-datasets' / self.dataset_id
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        review = datasets.export_review(self.root, self.dataset_id)
        first = datasets.export_dataset(self.root, self.dataset_id, True, review['revision'])
        self.assertEqual(first, datasets.export_dataset(self.root, self.dataset_id, True, review['revision']))
        content = base64.b64decode(first['data'])
        self.assertEqual(first['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(first['bytes'], len(content))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(set(archive.namelist()), {*before, 'dataset-export.json'})
            self.assertEqual(json.loads(archive.read('dataset-export.json')), review)
            for name, data in before.items():
                self.assertEqual(archive.read(name), data)
                self.assertEqual(review['files'][name]['sha256'], hashlib.sha256(data).hexdigest())
            restored = self.root / 'restored' / 'decoder-datasets' / self.dataset_id
            restored.mkdir(parents=True)
            for name in before:
                (restored / name).write_bytes(archive.read(name))
        self.assertEqual(datasets.read(self.root / 'restored', self.dataset_id), self.child)
        self.assertEqual(self.child['derivation']['parent_manifest_sha256'], datasets.digest(self.parent))
        sources = [source for row in self.child['derivation']['sources'] for source in row['parent_sources']]
        self.assertEqual(sources, [next(s for s in self.parent['sources'] if s['name'] == row['name'])
                                   for row in self.child['derivation']['sources']])
        self.assertFalse(review['includes_training_approvals'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root / 'decoder-trials').exists())
        self.assertFalse((self.root / 'decoder-dataset-exports').exists())

    def test_consent_stale_review_and_changed_implementation_rejected(self):
        review = datasets.export_review(self.root, self.dataset_id)
        for consent in (False, None, 1):
            with self.assertRaisesRegex(ValueError, 'Confirm'):
                datasets.export_dataset(self.root, self.dataset_id, consent, review['revision'])
        with self.assertRaisesRegex(ValueError, 'review changed'):
            datasets.export_dataset(self.root, self.dataset_id, True, 'stale')
        original = datasets.file_digest
        with patch.object(datasets, 'file_digest', side_effect=lambda path: 'changed' if Path(path).name == 'decoder_datasets.py' else original(path)):
            with self.assertRaisesRegex(ValueError, 'review changed'):
                datasets.export_dataset(self.root, self.dataset_id, True, review['revision'])

    def test_corrupt_content_rejected_after_review(self):
        review = datasets.export_review(self.root, self.dataset_id)
        (self.root / 'decoder-datasets' / self.dataset_id / 'documents.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            datasets.export_dataset(self.root, self.dataset_id, True, review['revision'])

    def test_dataset_without_tokenizer_or_derivation_can_export(self):
        dataset = datasets.prepare(self.root, [{'name': str(i), 'text': f'word{i}'} for i in range(3)], True)
        review = datasets.export_review(self.root, dataset['id'])
        exported = datasets.export_dataset(self.root, dataset['id'], True, review['revision'])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:
            self.assertEqual(set(archive.namelist()), {'documents.jsonl', 'manifest.json', 'dataset-export.json'})
            self.assertNotIn('derivation', json.loads(archive.read('manifest.json')))


if __name__ == '__main__':
    unittest.main()
