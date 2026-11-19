import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from backend.decoder_recipe import Decoder


class DecoderArtifactTest(unittest.TestCase):
    def test_roundtrip_preserves_modified_weights_and_cpu_predictions(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Decoder({})
            model.parameters['head'] *= 2
            path = Path(folder) / 'decoder.json'
            model.save(path)
            restored = Decoder.load(path)
            self.assertEqual(restored.config, model.config)
            np.testing.assert_array_equal(restored.logits([[0, 1, 2, 3]]), model.logits([[0, 1, 2, 3]]))
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_invalid_save_preserves_existing_artifact_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'decoder.json'
            model = Decoder({})
            model.save(path)
            before = path.read_bytes()
            for invalid in (float('nan'), float('inf'), 1e100):
                model.parameters['head'] = np.full((8, 16), invalid)
                with self.assertRaises(ValueError): model.save(path)
                self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_load_rejects_wrong_versions_shapes_names_and_nonfinite_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'decoder.json'
            for change in ('version', 'shape', 'name', 'nonfinite', 'config', 'oversized'):
                data = Decoder({}).artifact()
                if change == 'version': data['schema_version'] = True
                if change == 'shape': data['parameters']['head'] = [1, 2]
                if change == 'name': data['parameters']['unknown'] = []
                if change == 'nonfinite': data['parameters']['head'][0][0] = float('nan')
                if change == 'config': data['config']['width'] = 100000
                path.write_text(json.dumps(data))
                if change == 'oversized': path.write_bytes(b' ' * (4 * 1024 * 1024 + 1))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    Decoder.load(path)

    def test_failed_replace_removes_staging_file_and_preserves_destination(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'decoder.json'
            path.write_text('original')
            with patch.object(Path, 'replace', side_effect=OSError('fixture failure')):
                with self.assertRaises(OSError): Decoder({}).save(path)
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(list(Path(folder).iterdir()), [path])
