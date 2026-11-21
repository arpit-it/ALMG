import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class TrialAssessmentTest(unittest.TestCase):
    def test_incomplete_long_shared_or_resumed_records_are_not_quick_trial_evidence(self):
        records = [
            {'status':'canceled'},
            {'status':'completed','completed_steps':20},
            {'status':'completed','completed_steps':10,'review':{'config':{'steps':10},'execution_mode':'shared_backend'}},
            {'status':'completed','completed_steps':10,'review':{'config':{'steps':10},'execution_mode':'fresh_process','reference_resume_from':{}}},
        ]
        for record in records:
            with patch.object(training, 'read', return_value=record), patch.object(training.inputs, 'read') as inputs:
                with self.assertRaises(ValueError):
                    budget.assess_quick_trial(Path('/unused'), 'unused', {})
                inputs.assert_not_called()

    def test_unmeasured_trial_cannot_supply_measured_assessment(self):
        record = {'status':'completed','completed_steps':10,'review':{'config':{'steps':10},'execution_mode':'fresh_process'}}
        with patch.object(training, 'read', return_value=record), patch.object(training.feedback, 'measurements', return_value=None):
            with self.assertRaises(ValueError):
                budget.assess_quick_trial(Path('/unused'), 'unused', {})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires actual quick and separately approved larger trials')
    def test_assessment_preserves_scope_and_requested_timing_requires_actual_larger_run(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary); source, saved, base = corpus(root)
                config = {**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                quick = budget.review_quick_trial(root, source, saved, config)
                trial = isolated.run(root, True, source, saved, quick['trial_config'], quick['trial_budget_review']['resource_review'], uuid.uuid4().hex)
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                assessment = budget.assess_quick_trial(root, trial['id'], config)
                self.assertEqual(assessment['trial_source']['record_revision'], trial['revision'])
                self.assertTrue(assessment['trial_validation']['training_loss_decreased'])
                self.assertFalse(assessment['requested_update_budget_covered_by_trial'])
                self.assertFalse(assessment['compatible_requested_budget_timing_available'])
                self.assertFalse(assessment['training_approved']); self.assertFalse(assessment['release_approved'])
                same = budget.assess_quick_trial(root, trial['id'], quick['trial_config'])
                self.assertTrue(same['requested_update_budget_covered_by_trial'])
                self.assertTrue(same['compatible_requested_budget_timing_available'])
                with self.assertRaises(ValueError):
                    budget.assess_quick_trial(root, trial['id'], {**config,'learning_rate':.005})
                resource = assessment['requested_budget_review']['resource_review']
                for approved, confirmed in ((assessment,True),(resource,False),(quick['trial_budget_review']['resource_review'],True)):
                    with self.assertRaises(ValueError):
                        isolated.run(root, confirmed, source, saved, config, approved, uuid.uuid4().hex)
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                full = isolated.run(root, True, source, saved, config, resource, uuid.uuid4().hex)
                self.assertEqual(full['completed_steps'], 20)
                self.assertEqual(full['review']['source'], trial['review']['source'])
                after = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                updated = budget.assess_quick_trial(root, trial['id'], config)
                self.assertFalse(updated['requested_update_budget_covered_by_trial'])
                self.assertTrue(updated['compatible_requested_budget_timing_available'])
                self.assertTrue(any(s['record_id']==full['id'] for s in updated['requested_budget_review']['workflow_duration_estimate']['source_records']))
                self.assertEqual(after, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                profile = {'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
                with patch.object(training.hardware, 'hardware', return_value=profile):
                    blocked = budget.assess_quick_trial(root, trial['id'], config)
                self.assertFalse(blocked['feasible']); self.assertTrue(blocked['blockers'])
