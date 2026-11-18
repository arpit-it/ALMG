import io
import os
import json
import unittest
from unittest.mock import Mock, patch
from backend import lora_validation, studio


class LoraValidationTest(unittest.TestCase):
    def test_unsupported_host_has_clear_error_without_loading_mlx(self):
        with patch.object(lora_validation.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(ValueError, 'Apple silicon'):
                lora_validation.run()

    def test_runtime_route_requires_explicit_confirmation_and_returns_evidence(self):
        for confirmed in (None, False, 1, True):
            body = json.dumps({'confirmed': confirmed}).encode()
            handler = Mock(path='/runtime/lora-fixture', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            evidence = {'passed': True, 'rank': 2, 'base_weights_unchanged': True, 'reload_max_error': 0.0}
            with patch.object(lora_validation, 'run', return_value=evidence) as run:
                studio.Handler.do_POST(handler)
            if confirmed is True:
                run.assert_called_once_with()
                self.assertEqual(handler.respond.call_args.args[0], evidence)
            else:
                run.assert_not_called()
                self.assertEqual(handler.respond.call_args.args[1], 400)

    def test_generated_train_and_held_out_contexts_are_distinct(self):
        training = lora_validation.token_sequences(8)
        held_out = lora_validation.token_sequences(12)
        self.assertEqual(len(training), 4)
        self.assertEqual(len(held_out), 4)
        self.assertTrue(all(len(row) == 8 for row in training))
        self.assertTrue(all(len(row) == 12 for row in held_out))
        self.assertFalse({tuple(row) for row in training} & {tuple(row) for row in held_out})
        self.assertEqual(set(token for row in training for token in row), {0, 1, 2, 3})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in Apple silicon Metal fixture')
    def test_real_causal_language_model_lora_on_metal(self):
        result = lora_validation.run()
        self.assertTrue(result['passed'])
        self.assertLess(result['final_loss'], result['initial_loss'] * 0.1)
        self.assertGreaterEqual(result['held_out_next_token_accuracy'], 0.95)
        self.assertTrue(result['base_weights_unchanged'])
        self.assertEqual(result['reload_max_error'], 0.0)
        self.assertEqual(result['causal_prefix_max_error'], 0.0)
        self.assertTrue(result['generation_matches_fixture'])
        self.assertEqual(result['generated_tokens'], lora_validation.token_sequences(12)[0])
