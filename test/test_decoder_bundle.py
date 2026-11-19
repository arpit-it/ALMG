import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_bundle
from backend.decoder_recipe import Decoder
from backend.decoder_tokenizer import Tokenizer


class DecoderBundleTest(unittest.TestCase):
    def fixture(self, path):
        return decoder_bundle.save(path, Decoder({'vocab_size': 4}),
                                   Tokenizer.fit(['amber birch cedar dune']), {'seed': 7, 'steps': 100})

    def test_bundle_roundtrip_preserves_records_tokenizer_and_predictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bundle'
            manifest = self.fixture(path)
            model, tokenizer, restored = decoder_bundle.load(path)
            self.assertEqual(restored, manifest)
            self.assertEqual(tokenizer.decode(tokenizer.encode('amber dune')), 'amber dune')
            np.testing.assert_array_equal(model.logits([[0, 1]]), Decoder({'vocab_size': 4}).logits([[0, 1]]))
            self.assertEqual(set(manifest['files']), {'decoder.json', 'tokenizer.json'})

    def test_tampering_is_rejected_before_loading_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ('decoder.json', 'tokenizer.json'):
                path = Path(temporary) / name
                self.fixture(path)
                (path / name).write_text('{}')
                with patch.object(Decoder, 'load') as load:
                    with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                        decoder_bundle.load(path)
                    load.assert_not_called()

    def test_manifest_versions_training_and_tokenizer_binding_are_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            for change in ('version', 'stage', 'training', 'tokenizer', 'files'):
                path = Path(temporary) / change
                self.fixture(path)
                manifest = json.loads((path / 'manifest.json').read_text())
                if change == 'version': manifest['schema_version'] = True
                if change == 'stage': manifest['stages']['architecture'] = True
                if change == 'training': manifest['training']['steps'] = 1
                if change == 'tokenizer': manifest['tokenizer_sha256'] = 'changed'
                if change == 'files': manifest['files'] = {'../decoder.json': 'changed'}
                (path / 'manifest.json').write_text(json.dumps(manifest))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    decoder_bundle.load(path)

    def test_existing_destination_and_failed_staging_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bundle'
            self.fixture(path)
            original = (path / 'manifest.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'already exists'): self.fixture(path)
            self.assertEqual((path / 'manifest.json').read_bytes(), original)
            failed = Path(temporary) / 'failed'
            with patch.object(decoder_bundle, 'load', side_effect=ValueError('fixture failure')):
                with self.assertRaises(ValueError): self.fixture(failed)
            self.assertFalse(failed.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [path])
