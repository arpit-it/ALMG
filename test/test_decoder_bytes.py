"""Versioned fixed byte vocabulary and immutable prepared dataset compatibility."""
import json
import tempfile
from pathlib import Path
import unittest
from backend.decoder_tokenizer import Tokenizer, ByteTokenizer
from backend import decoder_datasets, decoder_dataset_training, decoder_bundle
from backend.decoder_recipe import Decoder


def documents():
    return [{'name': f'byte-{i}.txt', 'text': ('ab cd ef gh '*10)+f'unique{i}'} for i in range(6)]


class DecoderByteTokenizerTest(unittest.TestCase):
    def test_utf8_roundtrip_unseen_words_and_explicit_invalid_byte_rendering(self):
        tokenizer = ByteTokenizer.fit(['training only'])
        self.assertEqual(len(tokenizer.vocabulary), 256)
        self.assertEqual(tokenizer.decode(tokenizer.encode('naïve नमस्ते 🙂')), 'naïve नमस्ते 🙂')
        self.assertEqual(tokenizer.encode('e\u0301'), tokenizer.encode('é'))
        self.assertEqual(tokenizer.decode([255]), '\ufffd')
        restored = Tokenizer.restore(tokenizer.artifact())
        self.assertIsInstance(restored, ByteTokenizer)
        self.assertEqual(restored.fingerprint(), tokenizer.fingerprint())
        self.assertNotEqual(ByteTokenizer.fit(['different training']).fingerprint(), tokenizer.fingerprint())
        for value in ([], [True], [-1], [256], [0]*4097):
            with self.assertRaises(ValueError): tokenizer.decode(value)
        with self.assertRaises(ValueError): tokenizer.encode('x'*4097)
        for artifact in ({**tokenizer.artifact(), 'schema_version': True}, {**tokenizer.artifact(), 'encoding': 'latin1'},
                         {**tokenizer.artifact(), 'training_documents_sha256': 'bad'}):
            with self.assertRaises(ValueError): Tokenizer.restore(artifact)

    def test_preparation_does_not_refit_on_evaluation_or_change_word_datasets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            word = decoder_datasets.prepare(root, documents(), True)
            self.assertTrue(any(f['kind']=='out_of_training_vocabulary' for f in word['findings']))
            byte = decoder_datasets.prepare(root, documents(), True, 'utf8_bytes')
            self.assertFalse(byte['findings'])
            self.assertEqual(byte['tokenizer']['vocabulary_size'], 256)
            self.assertEqual(decoder_datasets.read(root, byte['id']), byte)
            manifest, tokenizer, records, batches = decoder_dataset_training.preflight(root, byte)
            self.assertEqual(manifest, byte)
            fitted = ByteTokenizer.fit([row['text'] for row in records if row['split']=='train'])
            self.assertEqual(fitted.fingerprint(), tokenizer.fingerprint())
            self.assertTrue(all(batches.values()))
            self.assertEqual(decoder_datasets.read(root, word['id']), word)
            path = root/'bundle'
            decoder_bundle.save(path, Decoder({'vocab_size':256}), tokenizer, {'seed':7}, pretraining_stage='pretraining_local')
            _, restored, _ = decoder_bundle.load(path)
            self.assertEqual(restored.decode(restored.encode('unseen')), 'unseen')
            with self.assertRaises(ValueError): decoder_datasets.prepare(root, documents(), True, 'unknown')

    def test_training_provenance_tampering_is_rejected_even_after_file_hash_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True, 'utf8_bytes')
            folder = root/'decoder-datasets'/manifest['id']
            artifact = json.loads((folder/'tokenizer.json').read_text())
            artifact['training_documents_sha256'] = '0'*64
            (folder/'tokenizer.json').write_text(json.dumps(artifact))
            manifest['files']['tokenizer.json'] = decoder_datasets.file_digest(folder/'tokenizer.json')
            manifest['tokenizer']['sha256'] = Tokenizer.restore(artifact).fingerprint()
            (folder/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'training partition'):
                decoder_datasets.read(root, manifest['id'])
