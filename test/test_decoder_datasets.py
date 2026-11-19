import json
from pathlib import Path
import tempfile
import unittest
from backend import decoder_datasets


def documents():
    return [{'name': f'doc-{index}.txt', 'text': 'amber birch cedar dune ' + f'unique{index}'} for index in range(6)]


class DecoderDatasetsTest(unittest.TestCase):
    def test_grouped_deduplication_has_disjoint_partitions_and_retains_source_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = documents()
            rows.append({'name': 'duplicate.txt', 'text': rows[0]['text'].replace(' ', '  ')})
            manifest = decoder_datasets.prepare(root, rows, True)
            self.assertEqual(manifest['input_documents'], 7)
            self.assertEqual(manifest['unique_documents'], 6)
            self.assertEqual(manifest['splits'], {'train': 4, 'validation': 1, 'test': 1})
            self.assertEqual(len(manifest['sources']), 7)
            self.assertTrue(any(row['kind'] == 'duplicate_document' for row in manifest['findings']))
            records = [json.loads(line) for line in (root/'decoder-datasets'/manifest['id']/'documents.jsonl').read_text().splitlines()]
            self.assertEqual(len({row['group'] for row in records}), 6)
            self.assertTrue(all(len(source['source_sha256']) == 64 for source in manifest['sources']))
            self.assertEqual(decoder_datasets.read(root, manifest['id']), manifest)
            self.assertFalse((root/'decoder-trials').exists())

    def test_evaluation_vocabulary_is_reported_without_leaking_into_tokenizer_fit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            folder = root/'decoder-datasets'/manifest['id']
            tokenizer = json.loads((folder/'tokenizer.json').read_text())
            records = [json.loads(line) for line in (folder/'documents.jsonl').read_text().splitlines()]
            for row in records:
                if row['split'] != 'train':
                    unique = row['text'].split()[-1]
                    self.assertNotIn(unique, tokenizer['vocabulary'])
                    self.assertTrue(any(finding.get('source') == row['name'] and finding['kind'] == 'out_of_training_vocabulary' for finding in manifest['findings']))

    def test_reordered_selection_is_reproducible_and_existing_dataset_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = decoder_datasets.prepare(root, documents(), True)
            path = root/'decoder-datasets'/first['id']/'manifest.json'
            before = path.read_bytes()
            second = decoder_datasets.prepare(root, list(reversed(documents())), True)
            self.assertNotEqual(first['id'], second['id'])
            self.assertEqual(first['dataset_sha256'], second['dataset_sha256'])
            self.assertEqual(first['sources'], second['sources'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(decoder_datasets.read(root, first['id']), first)

    def test_invalid_inputs_fail_before_publishing_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for rows in ([], documents()*3, [{'name': str(i), 'text': 'same four word text'} for i in range(3)],
                         [{'name': str(i), 'text': 'binary\x00'} for i in range(3)],
                         [{'name': str(i), 'text': 'a'*65537} for i in range(3)]):
                with self.assertRaises(ValueError): decoder_datasets.prepare(root, rows, True)
            with self.assertRaises(ValueError): decoder_datasets.prepare(root, documents(), False)
            self.assertFalse((root/'decoder-datasets').exists())

    def test_tampering_and_invalid_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            folder = root/'decoder-datasets'/manifest['id']
            (folder/'documents.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): decoder_datasets.read(root, manifest['id'])
            for dataset_id in ('../escape', None, 'invalid'):
                with self.assertRaises(ValueError): decoder_datasets.read(root, dataset_id)

    def test_original_bom_bytes_are_hashed_before_text_normalization(self):
        import base64, hashlib
        with tempfile.TemporaryDirectory() as temporary:
            rows = documents()
            original = b'\xef\xbb\xbf' + rows[0]['text'].encode('utf-8')
            rows.append({'name': 'bom-copy.txt', 'data': base64.b64encode(original).decode()})
            manifest = decoder_datasets.prepare(Path(temporary), rows, True)
            self.assertEqual(manifest['unique_documents'], 6)
            source = next(source for source in manifest['sources'] if source['name'] == 'bom-copy.txt')
            self.assertEqual(source['source_sha256'], hashlib.sha256(original).hexdigest())
            self.assertTrue(any(finding['kind'] == 'duplicate_document' for finding in manifest['findings']))

    def test_malformed_byte_payloads_do_not_publish_datasets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for payload in ('not base64!', '/w=='):
                rows = documents()
                rows[0] = {'name': 'bad.txt', 'data': payload}
                with self.assertRaises(ValueError): decoder_datasets.prepare(root, rows, True)
            self.assertFalse((root/'decoder-datasets').exists())
