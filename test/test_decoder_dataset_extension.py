import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_datasets as datasets


class DatasetExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parent = datasets.prepare(self.root, [
            {'name': 'a.txt', 'text': 'Amber birch cedar dune local text'},
            {'name': 'copy.txt', 'text': 'Amber birch cedar dune local text'},
            {'name': 'b.txt', 'text': 'Cedar dune amber birch second record'},
            {'name': 'c.txt', 'text': 'Dune amber birch cedar third record'},
        ], True, 'utf8_bytes')
        self.dataset_id = self.parent['id']

    def test_incremental_version_preserves_original_sources_and_new_raw_hash(self):
        folder = self.root / 'decoder-datasets' / self.dataset_id
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        raw = '\ufeffMaple cafe\u0301 leaves in a new local document'.encode('utf-8')
        child = datasets.extend_dataset(self.root, self.dataset_id, True, self.parent,
                                       [{'name': 'new.txt', 'data': base64.b64encode(raw).decode()}])
        self.assertNotEqual(child['id'], self.dataset_id)
        self.assertEqual((child['input_documents'], child['unique_documents']), (4, 4))
        self.assertEqual(child['status'], 'prepared_for_review')
        self.assertEqual(child['tokenizer']['format'], self.parent['tokenizer']['format'])
        self.assertEqual(datasets.read(self.root, child['id']), child)
        source = next(s for s in child['sources'] if s['name'] == 'new.txt')
        self.assertEqual(source['source_sha256'], hashlib.sha256(raw).hexdigest())
        derivation = child['derivation']
        self.assertEqual(derivation['operation'], 'append_local_documents')
        self.assertEqual(derivation['parent_manifest_sha256'], datasets.digest(self.parent))
        inherited = [s for row in derivation['sources'] for s in row['parent_sources']]
        self.assertEqual(sorted(s['source_sha256'] for s in inherited), sorted(s['source_sha256'] for s in self.parent['sources']))
        self.assertEqual(len(inherited), 4)  # Exact-deduplicated parent sources are still traceable.
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root / 'decoder-trials').exists())

    def test_consent_review_empty_and_capacity_fail_without_new_dataset(self):
        before = set((self.root / 'decoder-datasets').iterdir())
        valid = [{'name': 'new', 'text': 'a new distinct local record'}]
        changed = dict(self.parent, status='changed')
        for confirmed, reviewed, docs in ((False, self.parent, valid), (1, self.parent, valid),
                                           (True, changed, valid), (True, None, valid),
                                           (True, self.parent, []), (True, self.parent, valid * 14),
                                           (True, self.parent, [{'name': 'large', 'text': 'x' * 65537}])):
            with self.assertRaises(ValueError):
                datasets.extend_dataset(self.root, self.dataset_id, confirmed, reviewed, docs)
        self.assertEqual(before, set((self.root / 'decoder-datasets').iterdir()))
        self.assertFalse(list((self.root / 'decoder-datasets').glob('.prepare-*')))

    def test_duplicate_addition_keeps_source_provenance_and_separate_version(self):
        child = datasets.extend_dataset(self.root, self.dataset_id, True, self.parent,
                                       [{'name': 'new-copy', 'text': 'Amber birch cedar dune local text'}])
        self.assertEqual(child['unique_documents'], 3)
        self.assertEqual(child['input_documents'], 4)
        self.assertEqual(len(child['findings']), 1)
        self.assertEqual(child['findings'][0]['kind'], 'duplicate_document')
        self.assertIn('new-copy', [s['name'] for s in child['sources']])

    def test_word_parent_preserves_kind_and_corrupt_parent_cannot_extend(self):
        parent = datasets.prepare(self.root, [
            {'name': str(i), 'text': ' '.join(['amber','birch','cedar','dune'] * (i+1))}
            for i in range(3)], True)
        child = datasets.extend_dataset(self.root, parent['id'], True, parent,
                                       [{'name': 'extra', 'text': 'amber birch cedar dune extra'}])
        self.assertTrue(child['tokenizer'] is None or child['tokenizer']['format'] == 'almg-whitespace-tokenizer-v1')
        before = set((self.root / 'decoder-datasets').iterdir())
        (self.root / 'decoder-datasets' / self.dataset_id / 'documents.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            datasets.extend_dataset(self.root, self.dataset_id, True, self.parent, [{'name': 'new', 'text': 'local text'}])
        self.assertEqual(before, set((self.root / 'decoder-datasets').iterdir()))


if __name__ == '__main__':
    unittest.main()
