import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class CorpusTokenLimitTest(unittest.TestCase):
    def test_supported_budgets_preserve_recipe_controls_and_never_expand_request(self):
        base = {'schema_version': 7, 'optimizer': 'sgd', 'learning_rate': .001, 'schedule': 'warmup_cosine',
                'warmup_steps': 3, 'steps': 80, 'gradient_clip_norm': .5, 'weight_decay': 0.,
                'batch_size': 2, 'sequence_length': 8, 'gradient_accumulation_steps': 2,
                'compute_precision': 'float32', 'loss_scale': 1.}
        for config, expected in ((base, [(5,10),(5,20),(6,40),(7,80)]),
                                 ({**base,'schema_version':6,'steps':40},[(5,10),(5,20),(6,40)]),
                                 ({**base,'schema_version':8,'steps':20,'sequence_length':16},[(8,10),(8,20)]),
                                 ({**base,'schema_version':9,'steps':20,'batch_size':4,'gradient_accumulation_steps':4},[(9,10),(9,20)])):
            results = list(budget.smaller_budgets(config))
            self.assertEqual([(c['schema_version'],c['steps']) for c in results], expected)
            for candidate in results:
                self.assertEqual({k:v for k,v in candidate.items() if k not in ('schema_version','steps')},
                                 {k:v for k,v in config.items() if k not in ('schema_version','steps')})

    def test_invalid_limits_rejected_before_source_access(self):
        with patch.object(training, '_source') as source:
            for limit in (None, True, 0, -1, 1.5, '300', 2**63):
                with self.assertRaises(ValueError):
                    budget.review_limit(Path('/unused'), None, None, None, limit)
            source.assert_not_called()

    def test_read_only_selection_exact_cap_too_small_and_resource_blockers(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, saved, config = corpus(root)
            before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            full = budget.review(root, source, saved, config)['exposure']['full_workflow_optimizer_target_tokens']
            result = budget.review_limit(root, source, saved, config, full - 1)
            self.assertEqual(result['selected_config']['steps'], 10)
            self.assertFalse(result['training_approved'])
            self.assertFalse(result['release_approved'])
            self.assertTrue(result['considered_budgets'][0]['within_limit'])
            self.assertFalse(result['considered_budgets'][1]['within_limit'])
            self.assertEqual(budget.review_limit(root, source, saved, config, full)['selected_config']['steps'], 20)
            minimum = result['selected_budget_review']['exposure']['full_workflow_optimizer_target_tokens']
            with self.assertRaisesRegex(ValueError, 'No supported update budget'):
                budget.review_limit(root, source, saved, config, minimum - 1)
            profile = {'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},
                       'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware, 'hardware', return_value=profile):
                blocked = budget.review_limit(root, source, saved, config, full - 1)
            self.assertFalse(blocked['feasible'])
            self.assertTrue(blocked['blockers'])
            self.assertFalse(blocked['selected_budget_review']['training_approved'])
            self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires actual fixed-budget Metal training')
    def test_selected_budget_runs_within_cap_and_changed_budget_needs_new_review(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, saved, base = corpus(root)
                config = {**base, 'optimizer':kind, 'weight_decay':.01 if kind=='adamw' else 0.}
                full = budget.review(root, source, saved, config)['exposure']['full_workflow_optimizer_target_tokens']
                proposal = budget.review_limit(root, source, saved, config, full - 1)
                selected = proposal['selected_config']
                review = proposal['selected_budget_review']['resource_review']
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):
                    isolated.run(root, True, source, saved, config, review, uuid.uuid4().hex)
                with self.assertRaises(ValueError):
                    isolated.run(root, True, source, saved, selected, proposal, uuid.uuid4().hex)
                with self.assertRaises(ValueError):
                    isolated.run(root, False, source, saved, selected, review, uuid.uuid4().hex)
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                record = isolated.run(root, True, source, saved, selected, review, uuid.uuid4().hex)
                targets = 2 * sum(row['target_tokens'] for row in record['step_log'])
                self.assertEqual(record['completed_steps'], 10)
                self.assertEqual(targets, proposal['selected_budget_review']['exposure']['full_workflow_optimizer_target_tokens'])
                self.assertLessEqual(targets, full - 1)
                self.assertLessEqual(record['checkpoint_parameter_max_error'], 1e-7)
                self.assertLessEqual(record['checkpoint_optimizer_max_error'], 1e-7)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
