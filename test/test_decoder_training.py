import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from backend import decoder_training, recipe_contracts, studio


class DecoderTrainingTest(unittest.TestCase):
    def test_unavailable_hardware_is_rejected_before_constructing_model(self):
        initialize = Mock()
        with patch.object(decoder_training.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(ValueError, 'Apple silicon'):
                decoder_training.run(initialize)
        initialize.assert_not_called()

    def test_training_route_requires_explicit_confirmation(self):
        for confirmed in (None, False, 1, True):
            body = json.dumps({'confirmed': confirmed}).encode()
            handler = Mock(path='/runtime/decoder-training', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            with patch.object(decoder_training, 'run', return_value={'passed': True}) as run:
                studio.Handler.do_POST(handler)
            if confirmed is True:
                run.assert_called_once_with(recipe_contracts.initialize_recipe)
                self.assertEqual(handler.respond.call_args.args[0], {'passed': True})
            else:
                run.assert_not_called()
                self.assertEqual(handler.respond.call_args.args[1], 400)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in actual Metal verification')
    def test_all_fresh_student_parameters_train_and_generate_causally(self):
        result = decoder_training.run(recipe_contracts.initialize_recipe)
        self.assertTrue(result['passed'])
        self.assertEqual(result['trainable_parameters'], 704)
        self.assertEqual(result['frozen_parameters'], 0)
        self.assertEqual(len(result['updated_parameter_groups']), 9)
        self.assertFalse(result['pretrained_weights_loaded'])
        self.assertLess(result['final_loss'], result['initial_loss'] * .1)
        self.assertGreaterEqual(result['held_out_next_token_accuracy'], .95)
        self.assertEqual(result['generated_tokens'], [index % 4 for index in range(12)])
        self.assertEqual(result['causal_prefix_max_error'], 0)
        self.assertLess(result['cpu_inference_max_error'], 1e-5)
        self.assertEqual(result['artifact_reload_max_error'], 0)
        self.assertEqual(result['artifact_format'], 'almg-decoder-v1')
        self.assertTrue(result['temporary_artifact_removed'])
        self.assertTrue(result['tokenizer']['artifact_roundtrip'])
        self.assertTrue(result['bundle']['artifact_roundtrip'])
        self.assertEqual(result['checkpoint']['completed_steps'], 50)
        self.assertEqual(result['checkpoint']['resumed_steps'], 50)
        self.assertLess(result['checkpoint']['uninterrupted_max_error'], 1e-6)
        self.assertTrue(result['checkpoint']['temporary_checkpoint_removed'])
        self.assertEqual(result['bundle']['format'], 'almg-decoder-bundle-v1')
        self.assertEqual(set(result['bundle']['verified_files']), {'decoder.json', 'tokenizer.json'})
        self.assertEqual(result['tokenizer']['fit_source'], 'training_documents_only')
        self.assertEqual(result['generated_text'], 'amber birch cedar dune amber birch cedar dune amber birch cedar dune')

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in actual Metal verification')
    def test_durable_interruption_reuses_saved_checkpoint_and_keeps_bundle(self):
        import tempfile
        from pathlib import Path
        from backend import decoder_bundle
        original_save = decoder_bundle.save
        def interrupt(destination, *args):
            if Path(destination).name == 'bundle':
                raise RuntimeError('Fixture stop before final artifact')
            return original_save(destination, *args)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'artifacts'
            with patch.object(decoder_bundle, 'save', side_effect=interrupt):
                with self.assertRaisesRegex(RuntimeError, 'Fixture stop'):
                    decoder_training.run(recipe_contracts.initialize_recipe, work_directory=workspace)
            self.assertTrue((workspace / 'step-50' / 'manifest.json').is_file())
            result = decoder_training.run(recipe_contracts.initialize_recipe, work_directory=workspace)
            self.assertTrue(result['checkpoint']['reused_existing_checkpoint'])
            self.assertFalse(result['temporary_artifact_removed'])
            self.assertTrue((workspace / 'bundle' / 'manifest.json').is_file())
            decoder_bundle.load(workspace / 'bundle')

    def test_cancel_before_work_never_initializes_or_creates_artifacts(self):
        import tempfile
        from pathlib import Path
        initialize = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'artifacts'
            with self.assertRaises(decoder_training.Cancelled):
                decoder_training.run(initialize, work_directory=workspace, stop=lambda: True)
            initialize.assert_not_called()
            self.assertFalse(workspace.exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in actual Metal verification')
    def test_cancel_at_saved_checkpoint_and_resume_real_training(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'artifacts'
            stop = lambda: (workspace / 'step-50' / 'manifest.json').is_file()
            with self.assertRaises(decoder_training.Cancelled):
                decoder_training.run(recipe_contracts.initialize_recipe, work_directory=workspace, stop=stop)
            self.assertTrue(stop())
            self.assertFalse((workspace / 'bundle').exists())
            result = decoder_training.run(recipe_contracts.initialize_recipe, work_directory=workspace)
            self.assertTrue(result['checkpoint']['reused_existing_checkpoint'])
            self.assertEqual(result['held_out_next_token_accuracy'], 1)
