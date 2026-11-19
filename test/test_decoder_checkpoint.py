from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import numpy as np
from backend import decoder_checkpoint
from backend.decoder_recipe import Decoder
from backend.decoder_tokenizer import Tokenizer


class DecoderCheckpointTest(unittest.TestCase):
    def setup_checkpoint(self, folder):
        model = Decoder({'vocab_size': 4})
        model.parameters['head'] *= 2
        tokenizer = Tokenizer.fit(['amber birch cedar dune'])
        expected = decoder_checkpoint.revision(model.config, tokenizer, ['amber birch cedar dune'])
        decoder_checkpoint.save(folder, model, tokenizer, expected, 50)
        return model, tokenizer, expected

    def test_checkpoint_reloads_exact_weights_and_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'checkpoint'
            original, tokenizer, expected = self.setup_checkpoint(folder)
            restored, restored_tokenizer, lineage = decoder_checkpoint.load(folder, expected)
            np.testing.assert_array_equal(restored.logits([[0, 1, 2]]), original.logits([[0, 1, 2]]))
            self.assertEqual(tokenizer.fingerprint(), restored_tokenizer.fingerprint())
            self.assertEqual(lineage['completed_steps'], 50)
            self.assertEqual(len(lineage['manifest_sha256']), 64)

    def test_changed_inputs_or_optimizer_settings_cannot_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'checkpoint'
            _, _, expected = self.setup_checkpoint(folder)
            for field, value in (('training_text_sha256', 'changed'), ('learning_rate', .1),
                                 ('total_steps', 200), ('optimizer', 'other'), ('tokenizer_sha256', 'changed')):
                changed = deepcopy(expected)
                changed[field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'training revision'):
                    decoder_checkpoint.load(folder, changed)

    def test_invalid_progress_and_training_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Decoder({'vocab_size': 4})
            tokenizer = Tokenizer.fit(['amber birch cedar dune'])
            expected = decoder_checkpoint.revision(model.config, tokenizer, ['amber birch cedar dune'])
            for step in (-1, True, 100, 101):
                with self.assertRaises(ValueError):
                    decoder_checkpoint.save(Path(temporary) / 'invalid', model, tokenizer, expected, step)
            for total, rate in ((True, .05), (1001, .05), (100, float('nan')), (100, 0)):
                with self.assertRaises(ValueError):
                    decoder_checkpoint.revision(model.config, tokenizer, [], total, rate)
