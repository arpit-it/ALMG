import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_dataset_training, decoder_datasets, decoder_trials, recipe_contracts, decoder_bundle


def documents():
    words = ['amber', 'birch', 'cedar', 'dune']
    return [{'name': f'doc-{index}.txt', 'text': ' '.join(words[(index + step) % 4] for step in range(8 + index))}
            for index in range(6)]


class DecoderDatasetTrainingTest(unittest.TestCase):
    def test_preflight_accepts_only_exact_review_and_binds_approval_without_starting_model(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            selected, tokenizer, rows, batches = decoder_dataset_training.preflight(root, manifest)
            self.assertEqual(selected, manifest)
            self.assertEqual(len(tokenizer.vocabulary), 4)
            self.assertTrue(all(batches.values()))
            submit = Mock()
            record = decoder_trials.start(root, True, submit, dataset=manifest)
            self.assertEqual(record['dataset'], manifest)
            self.assertEqual(record['specification']['scope'], 'reviewed_local_text_trial')
            self.assertEqual(record['specification']['dataset_manifest_sha256'], decoder_bundle.digest(manifest))
            with patch.object(decoder_dataset_training, 'run', return_value={'metrics': {'passed': True}}) as train:
                decoder_trials.execute(root, record['id'])
            self.assertEqual(train.call_args.args, (recipe_contracts.initialize_recipe, root, manifest))
            self.assertEqual(decoder_trials.read(root, record['id'])['status'], 'complete')

    def test_cross_split_overlap_blocks_planning_and_admission_before_model_or_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            words = [f'w{i}' for i in range(40)]
            dataset = decoder_datasets.prepare(root, [
                {'name': f'near-{i}', 'text': ' '.join(words + [f'unique{i}'])}
                for i in range(6)], True, 'utf8_bytes')
            folder = root / 'decoder-datasets' / dataset['id']
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            submit, planner = Mock(), Mock()
            with patch.object(recipe_contracts, 'initialize_recipe') as initialize:
                for action in (
                    lambda: decoder_trials.start(root, True, submit, dataset=dataset),
                    lambda: decoder_trials.propose(root, 'Train local text', planner, dataset=dataset),
                    lambda: decoder_dataset_training.run(initialize, root, dataset, root / 'artifacts'),
                ):
                    with self.assertRaisesRegex(ValueError, '9 near-duplicate document pairs'):
                        action()
                initialize.assert_not_called()
            submit.assert_not_called()
            planner.assert_not_called()
            self.assertEqual(decoder_trials.list_trials(root), [])
            self.assertFalse((root / 'artifacts').exists())
            self.assertFalse((root / 'decoder-dataset-audits').exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_admission_recomputes_overlap_instead_of_trusting_saved_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = decoder_datasets.prepare(root, documents(), True)
            report = decoder_datasets.audit(root, dataset['id'], True)
            self.assertEqual(report['cross_split_pairs'], 0)
            with patch.object(decoder_datasets, 'quality_report', return_value={'cross_split_pairs': 1}) as check:
                with self.assertRaisesRegex(ValueError, 'contamination check blocked'):
                    decoder_dataset_training.preflight(root, dataset)
                check.assert_called_once_with(root, dataset['id'])
            self.assertIn('decoder_datasets.py', decoder_trials.specification(dataset)['components'])

    def test_changed_review_or_vocabulary_findings_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            changed = {**manifest, 'unique_documents': 99}
            with self.assertRaisesRegex(ValueError, 'review changed'):
                decoder_trials.start(root, True, Mock(), dataset=changed)
            bad = decoder_datasets.prepare(root, [{'name': f'bad-{i}', 'text': f'amber birch cedar dune unique{i}'} for i in range(6)], True)
            with self.assertRaisesRegex(ValueError, 'vocabulary findings'):
                decoder_trials.start(root, True, Mock(), dataset=bad)
            self.assertEqual(decoder_trials.list_trials(root), [])
            with self.assertRaisesRegex(ValueError, 'change data scope'):
                decoder_trials.start(root, True, Mock(), trial_id='a'*32, dataset=manifest)

    def test_pending_dataset_tampering_is_rejected_before_training(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            record = decoder_trials.start(root, True, Mock(), dataset=manifest)
            (root/'decoder-datasets'/manifest['id']/'documents.jsonl').write_text('{}\n')
            with patch.object(decoder_dataset_training, 'run') as train:
                decoder_trials.execute(root, record['id'])
                train.assert_not_called()
            self.assertEqual(decoder_trials.read(root, record['id'])['status'], 'interrupted')

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in actual Metal verification')
    def test_real_approved_local_text_training_produces_valid_cpu_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            result = decoder_dataset_training.run(recipe_contracts.initialize_recipe, root, manifest, root/'artifacts')
            self.assertTrue(result['metrics']['passed'])
            self.assertGreaterEqual(result['metrics']['held_out_next_token_accuracy'], .8)
            self.assertLess(result['cpu_inference_max_error'], 1e-5)
            model, tokenizer, record = decoder_bundle.load(root/'artifacts'/'bundle')
            self.assertIn('pretraining_local', record['stages'])
            self.assertEqual(record['training']['dataset_sha256'], manifest['dataset_sha256'])
            self.assertEqual(model.config['vocab_size'], len(tokenizer.vocabulary))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Opt-in actual Metal verification')
    def test_real_local_dataset_checkpoint_survives_cancel_and_resume(self):
        from backend import decoder_training
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = decoder_datasets.prepare(root, documents(), True)
            workspace = root/'artifacts'
            stop = lambda: (workspace/'step-50'/'manifest.json').is_file()
            with self.assertRaises(decoder_training.Cancelled):
                decoder_dataset_training.run(recipe_contracts.initialize_recipe, root, manifest, workspace, stop=stop)
            self.assertTrue(stop())
            self.assertFalse((workspace/'bundle').exists())
            result = decoder_dataset_training.run(recipe_contracts.initialize_recipe, root, manifest, workspace)
            self.assertTrue(result['checkpoint']['reused_existing_checkpoint'])
            self.assertTrue(result['metrics']['passed'])
            decoder_bundle.load(workspace/'bundle')
