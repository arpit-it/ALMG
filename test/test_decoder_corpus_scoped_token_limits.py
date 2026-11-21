import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class ScopedTokenLimitTest(unittest.TestCase):
    def test_each_limit_is_validated_before_source_access(self):
        with patch.object(training, '_source') as source:
            for invalid in (True, 0, -1, 1.5, '130', 2**63):
                with self.assertRaises(ValueError):
                    budget.review_limit(Path('/unused'), None, None, None, 1000, invalid)
                with self.assertRaises(ValueError):
                    budget.review_limit(Path('/unused'), None, None, None, invalid, 130)
            with self.assertRaises(ValueError):
                budget.review_limit(Path('/unused'), None, None, None)
            source.assert_not_called()

    def test_recorded_and_workflow_limits_apply_independently_and_together_without_writes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, saved, config = corpus(root)
            before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            small = budget.review(root, source, saved, {**config, 'steps':10})['exposure']
            full = budget.review(root, source, saved, config)['exposure']
            r = small['recorded_training_target_tokens']; w = small['full_workflow_optimizer_target_tokens']
            for workflow, recorded in ((None,r),(full['full_workflow_optimizer_target_tokens'],r),
                                       (w,full['recorded_training_target_tokens']),(w,r)):
                proposal = budget.review_limit(root, source, saved, config, workflow, recorded)
                self.assertEqual(proposal['selected_config']['steps'], 10)
                self.assertEqual(proposal['max_workflow_optimizer_target_tokens'], workflow)
                self.assertEqual(proposal['max_recorded_training_target_tokens'], recorded)
                self.assertEqual(proposal['considered_budgets'][0]['recorded_training_target_tokens'], r)
                self.assertFalse(proposal['training_approved'])
            exact = budget.review_limit(root, source, saved, config, None, full['recorded_training_target_tokens'])
            self.assertEqual(exact['selected_config']['steps'], 20)
            for workflow, recorded in ((full['full_workflow_optimizer_target_tokens'],r-1),
                                       (w-1,full['recorded_training_target_tokens'])):
                with self.assertRaisesRegex(ValueError, 'No supported update budget'):
                    budget.review_limit(root, source, saved, config, workflow, recorded)
            profile = {'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},
                       'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware, 'hardware', return_value=profile):
                blocked = budget.review_limit(root, source, saved, config, None, r)
            self.assertFalse(blocked['feasible'])
            self.assertTrue(blocked['blockers'])
            self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires actual fixed-budget Metal training')
    def test_confirmed_run_respects_both_scopes_and_cannot_expand_with_old_review(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, saved, base = corpus(root)
                config = {**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                small = budget.review(root, source, saved, {**config,'steps':10})['exposure']
                workflow = small['full_workflow_optimizer_target_tokens']
                recorded = small['recorded_training_target_tokens']
                proposal = budget.review_limit(root, source, saved, config, workflow, recorded)
                resource = proposal['selected_budget_review']['resource_review']
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):
                    isolated.run(root, True, source, saved, config, resource, uuid.uuid4().hex)
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                result = isolated.run(root, True, source, saved, proposal['selected_config'], resource, uuid.uuid4().hex)
                targets = sum(row['target_tokens'] for row in result['step_log'])
                self.assertEqual(result['completed_steps'], 10)
                self.assertLessEqual(targets, recorded)
                self.assertLessEqual(2*targets, workflow)
                self.assertLessEqual(result['checkpoint_parameter_max_error'], 1e-7)
                self.assertLessEqual(result['checkpoint_optimizer_max_error'], 1e-7)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
