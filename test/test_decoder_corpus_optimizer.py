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
                blocked = training.review(root, source, saved, {**settings, 'gradient_accumulation_steps': 2})
                self.assertFalse(blocked['feasible'])
                self.assertTrue(any('divide evenly' in reason for reason in blocked['blockers']))
                profile['available_memory_bytes'] = 1
                with self.assertRaises(ValueError): training.run(root, True, source, saved, settings, approved)
            self.assertFalse((root/'decoder-corpus-optimizer-runs').exists())
            for values in ({'compute_precision': 'mixed_float16', 'loss_scale': 1.0}, {'sequence_length': 4}):
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

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real masked Metal gradients')
    def test_unequal_masked_windows_accumulate_by_tokens_and_resume_exactly(self):
        import numpy as np
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, settings = corpus(root)
            windows = json.loads((root/'decoder-corpus-inputs'/saved['id']/'windows.json').read_text())['train']
            indices, arrays = training.batch_arrays(windows, 0, 2)
            self.assertEqual(indices, [0, 1])
            self.assertNotEqual(int(arrays[2][0].sum()), int(arrays[2][1].sum()))
            for kind in ('sgd', 'adamw'):
                results = []
                for accumulation in (1, 2):
                    c = {**settings, 'optimizer': kind, 'weight_decay': .01 if kind == 'adamw' else 0., 'batch_size': 2, 'gradient_accumulation_steps': accumulation}
                    approved = training.review(root, source, saved, c)
                    self.assertTrue(approved['feasible'])
                    record = training.run(root, True, source, saved, c, approved); results.append(record)
                    self.assertEqual(record['schema_version'], 3)
                    self.assertLessEqual(record['full_batch_gradient_max_error'], 1e-5)
                    self.assertLessEqual(record['checkpoint_parameter_max_error'], 1e-7)
                    self.assertLessEqual(record['checkpoint_optimizer_max_error'], 1e-7)
                    self.assertEqual(record['scheduler_completed_steps'], 20)
                    for step, entry in enumerate(record['step_log']):
                        indices, arrays = training.batch_arrays(windows, step, 2)
                        self.assertEqual(entry['window_indices'], indices)
                        self.assertEqual(entry['target_tokens'], int(arrays[2].sum()))
                        self.assertEqual(entry['microbatches'], accumulation)
                    self.assertEqual(training.read(root, record['id']), record)
                models = [training.PlannedDecoder.load(training._folder(root, record['id'])/'trained-model.json') for record in results]
                self.assertLess(max(float(np.max(np.abs(models[0].parameters[name]-models[1].parameters[name]))) for name in models[0].parameters), 1e-5)
                record = deepcopy(results[-1]); record['step_log'][0]['target_tokens'] += 1
                record['revision'] = training.digest({k:v for k,v in record.items() if k != 'revision'})
                (training._folder(root, record['id'])/'record.json').write_text(json.dumps(record))
                with self.assertRaises(ValueError): training.read(root, record['id'])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires mixed FP16 Metal computation')
    def test_mixed_precision_corpus_unscales_accumulates_restores_fp32_masters(self):
        import numpy as np
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, settings = corpus(root)
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            for kind in ('sgd', 'adamw'):
                c = {**settings, 'optimizer': kind, 'weight_decay': .01 if kind == 'adamw' else 0., 'batch_size': 2,
                     'gradient_accumulation_steps': 2, 'compute_precision': 'mixed_float16', 'loss_scale': 128.0}
                approved = training.review(root, source, saved, c)
                fp32 = training.review(root, source, saved, {**c, 'compute_precision': 'float32', 'loss_scale': 1.0})
                self.assertEqual(approved['estimates']['required_available_memory_bytes'], fp32['estimates']['required_available_memory_bytes'])
                record = training.run(root, True, source, saved, c, approved)
                self.assertLess(record['final_losses']['train'], record['initial_losses']['train'])
                self.assertEqual(record['compute_precision'], 'mixed_float16'); self.assertEqual(record['loss_scale'], 128)
                self.assertLessEqual(record['full_batch_gradient_max_error'], 1e-3)
                self.assertLessEqual(record['initial_precision_loss_difference'], .05)
                self.assertLessEqual(record['compute_fp32_logits_max_error'], .05)
                self.assertLessEqual(record['causal_prefix_max_error'], 1e-5)
                self.assertLessEqual(record['cpu_metal_max_error'], 1e-5)
                self.assertLessEqual(record['checkpoint_parameter_max_error'], 1e-7)
                self.assertLessEqual(record['checkpoint_optimizer_max_error'], 1e-7)
                self.assertEqual(record['scheduler_completed_steps'], 20)
                folder = training._folder(root, record['id'])
                model, state = training.optimizer.restore(folder/'step-10', c, approved['revision'])
                self.assertTrue(all(value.dtype == np.float32 for value in model.parameters.values()))
                self.assertTrue(all(value.dtype == np.float32 for part in ('m', 'v') for value in state[part].values()))
                self.assertEqual(training.read(root, record['id']), record)
                self.assertTrue(all(path.read_bytes() == data for path, data in before.items()))
                changed = deepcopy(record); changed['loss_scale'] = 1.; changed['revision'] = training.digest({k:v for k,v in changed.items() if k != 'revision'})
                (folder/'record.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError): training.read(root, record['id'])
