import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class QuickTrialPlanTest(unittest.TestCase):
    def test_smallest_budget_preserves_controls_and_resource_denials_without_execution(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, base = corpus(root)
            config = {**base,'schema_version':7,'steps':80}
            before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(training, 'run') as run:
                proposal = budget.review_quick_trial(root, source, saved, config)
                run.assert_not_called()
            self.assertEqual(proposal['requested_config'], config)
            self.assertEqual(proposal['trial_config']['steps'], 10)
            self.assertEqual(proposal['trial_config']['schema_version'], 5)
            self.assertEqual({k:v for k,v in proposal['trial_config'].items() if k not in ('steps','schema_version')},
                             {k:v for k,v in config.items() if k not in ('steps','schema_version')})
            self.assertFalse(proposal['training_approved']); self.assertFalse(proposal['release_approved'])
            self.assertFalse(proposal['compatible_trial_timing_available'])
            profile = {'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},
                       'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware, 'hardware', return_value=profile):
                blocked = budget.review_quick_trial(root, source, saved, config)
            self.assertFalse(blocked['feasible']); self.assertTrue(blocked['blockers'])
            self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_invalid_inputs_and_unknown_order_cannot_create_trial_proposals(self):
        with self.assertRaises(ValueError):
            budget.review_quick_trial(Path('/unused'), None, None, None)
        with patch.object(training, 'configuration', return_value={'schema_version':10}), patch.object(training, '_source') as source:
            with self.assertRaises(ValueError):
                budget.review_quick_trial(Path('/unused'), None, {'review':{'sequence_length':4}}, {})
            source.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real independently confirmed quick-trial calibration')
    def test_trial_unblocks_only_its_exact_duration_budget_and_keeps_full_training_unapproved(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary); source, saved, base = corpus(root)
                config = {**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                with self.assertRaises(ValueError):
                    budget.review_limit(root, source, saved, config, max_estimated_workflow_seconds=1000)
                proposal = budget.review_quick_trial(root, source, saved, config)
                selected = proposal['trial_config']; resource = proposal['trial_budget_review']['resource_review']
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                for settings, approved, confirmed in ((selected,proposal,True),(config,resource,True),(selected,resource,False)):
                    with self.assertRaises(ValueError):
                        isolated.run(root, confirmed, source, saved, settings, approved, uuid.uuid4().hex)
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                actual = isolated.run(root, True, source, saved, selected, resource, uuid.uuid4().hex)
                self.assertEqual(actual['completed_steps'], 10)
                self.assertLessEqual(actual['checkpoint_parameter_max_error'], 1e-7)
                self.assertLessEqual(actual['checkpoint_optimizer_max_error'], 1e-7)
                after = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                updated = budget.review_quick_trial(root, source, saved, config)
                self.assertTrue(updated['compatible_trial_timing_available'])
                work = updated['trial_budget_review']['workflow_duration_estimate']
                self.assertTrue(any(s['record_id']==actual['id'] for s in work['source_records']))
                limited = budget.review_limit(root, source, saved, config, max_estimated_workflow_seconds=work['estimated_seconds']*2)
                self.assertEqual(limited['selected_config']['steps'], 10)
                larger = next(c for c in limited['considered_budgets'] if c['config']['steps']==20)
                self.assertIsNone(larger['estimated_workflow_seconds'])
                self.assertFalse(larger['within_limit'])
                self.assertFalse(limited['training_approved'])
                self.assertEqual(after, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
