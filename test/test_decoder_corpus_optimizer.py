from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_corpus_optimizer as training, decoder_corpus_inputs as inputs
from test_decoder_corpus_inputs import fixture, permissions


def corpus(root):
    source, dataset = fixture(root); dataset = permissions(root, dataset)
    approved = inputs.review(root, source['plan_id'], source, dataset, 8)
    saved = inputs.save(root, source['plan_id'], True, source, dataset, 8, approved)
    settings = {**training.optimizer.DEFAULT, 'schema_version': 5, 'steps': 20, 'batch_size': 1,
                'sequence_length': 8, 'gradient_accumulation_steps': 1, 'compute_precision': 'float32', 'loss_scale': 1.0}
    return source, saved, settings


class CorpusOptimizerTest(unittest.TestCase):
    def test_requires_current_snapshot_consent_and_resource_approval_before_writes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, settings = corpus(root)
            profile = {'system': 'Darwin', 'machine': 'arm64', 'metal_available': True, 'metal_device': {}, 'available_memory_bytes': 8*1024**3, 'free_disk_bytes': 8*1024**3, 'errors': []}
            with patch.object(training.hardware, 'hardware', return_value=profile):
                approved = training.review(root, source, saved, settings)
                self.assertTrue(approved['feasible'])
                with self.assertRaises(ValueError): training.run(root, False, source, saved, settings, approved)
                changed = deepcopy(approved); changed['config']['steps'] = 10
                with self.assertRaises(ValueError): training.run(root, True, source, saved, settings, changed)
                profile['available_memory_bytes'] = 1
                with self.assertRaises(ValueError): training.run(root, True, source, saved, settings, approved)
            self.assertFalse((root/'decoder-corpus-optimizer-runs').exists())
            for values in ({'compute_precision': 'mixed_float16', 'loss_scale': 128.0}, {'batch_size': 2}, {'gradient_accumulation_steps': 2}, {'sequence_length': 4}):
                with self.assertRaises(ValueError): training.configuration({**settings, **values}, 8)
            changed = deepcopy(saved); changed['review']['sequence_length'] = 4
            with self.assertRaises(ValueError): training.review(root, source, changed, settings)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires actual Apple silicon Metal')
    def test_real_corpus_optimizers_reduce_loss_restore_state_and_generate_reloaded_text(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, settings = corpus(root)
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            records = []
            for kind in ('sgd', 'adamw'):
                c = {**settings, 'optimizer': kind, 'weight_decay': .01 if kind == 'adamw' else 0.0}
                approved = training.review(root, source, saved, c)
                record = training.run(root, True, source, saved, c, approved); records.append(record)
                self.assertLess(record['final_losses']['train'], record['initial_losses']['train'])
                self.assertEqual(record['checkpoint_restored_steps'], 10)
                self.assertEqual(record['completed_steps'], 20); self.assertEqual(record['scheduler_completed_steps'], 20)
                self.assertEqual(record['checkpoint_parameter_max_error'], 0)
                self.assertEqual(record['checkpoint_optimizer_max_error'], 0)
                self.assertEqual(record['step_log'][10]['step'], 11)
                self.assertEqual(record['step_log'][10]['window_index'], 10 % 6)
                self.assertTrue(all(entry['target_tokens'] > 0 for entry in record['step_log']))
                self.assertLessEqual(record['cpu_metal_max_error'], 1e-5)
                self.assertEqual(len(record['generated_text'].split()), 11)
                self.assertTrue(set(record['generated_text'].split()) <= {'amber', 'birch', 'cedar', 'dune'})
                self.assertFalse(record['pretrained_student_weights_loaded']); self.assertFalse(record['release_approved'])
                self.assertEqual(training.read(root, record['id']), record)
                self.assertTrue(all(path.read_bytes() == data for path, data in before.items()))
            self.assertEqual(training.history(root, source, saved), records)
            path = root/'decoder-corpus-optimizer-runs'/records[0]['id']/'tokenizer.json'
            path.write_text('{}')
            with self.assertRaises(ValueError): training.read(root, records[0]['id'])
