import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class TrainingResumeBudgetTest(unittest.TestCase):
    def test_unknown_order_rejected_before_resource_review(self):
        with patch.object(training, 'read', return_value={'review': {'config': {'schema_version': 10}}}), patch.object(isolated, 'review_training_resume') as review:
            with self.assertRaises(ValueError):
                budget.review_training_resume(Path('/unused'), 'unused')
            review.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real saved training-phase recovery')
    def test_planned_targets_match_resumes_before_and_after_midpoint(self):
        for kind in ('sgd', 'adamw'):
            for retained in (7, 11):
                with self.subTest(optimizer=kind, retained=retained), TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source, saved, base = corpus(root)
                    config = {**base, 'optimizer': kind, 'batch_size': 2, 'gradient_accumulation_steps': 2,
                              'weight_decay': .01 if kind == 'adamw' else 0.}
                    approved = training.review(root, source, saved, config)
                    token = uuid.uuid4().hex
                    original = training.optimizer.update
                    calls = 0
                    def stop(*args):
                        nonlocal calls
                        value = original(*args)
                        calls += 1
                        if calls == config['steps'] + retained:
                            training.run_cancellation.request(root, approved, token, True)
                        return value
                    with patch.object(training.optimizer, 'update', side_effect=stop):
                        parent = training.run(root, True, source, saved, config, approved, request_id=token)
                    self.assertEqual(parent['cancellation_phase'], 'checkpointed_training')
                    self.assertEqual(parent['completed_steps'], retained)
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    proposal = budget.review_training_resume(root, parent['id'])
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    self.assertFalse(proposal['training_approved'])
                    self.assertFalse(proposal['release_approved'])
                    e = proposal['exposure']
                    self.assertEqual(e['optimizer_updates'], 20 - retained)
                    self.assertEqual(e['restore_step'], retained)
                    self.assertEqual(e['comparison_reference_target_tokens'], 0)
                    self.assertIsNone(proposal['workflow_duration_estimate'])
                    with self.assertRaises(ValueError):
                        isolated.run_training_resume(root, parent['id'], True, proposal, uuid.uuid4().hex)
                    with self.assertRaises(ValueError):
                        isolated.run_training_resume(root, parent['id'], False, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    completed = isolated.run_training_resume(root, parent['id'], True, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(completed['training_updates_executed'], 20 - retained)
                    self.assertEqual(completed['reference_updates_executed'], 0)
                    self.assertEqual(sum(row['target_tokens'] for row in completed['step_log'][retained:]), e['recorded_training_target_tokens'])
                    self.assertEqual(e['full_workflow_optimizer_target_tokens'], e['recorded_training_target_tokens'])
                    self.assertLessEqual(completed['checkpoint_parameter_max_error'], 1e-7)
                    self.assertLessEqual(completed['checkpoint_optimizer_max_error'], 1e-7)
                    work = budget.review_training_resume(root, parent['id'])['workflow_duration_estimate']
                    self.assertIsNotNone(work)
                    self.assertFalse(work['measured'])
                    self.assertTrue(any(row['record_id'] == completed['id'] for row in work['source_records']))
                    self.assertTrue(all(p.read_bytes() == value for p, value in before.items()))
                    with self.assertRaises(ValueError):
                        budget.review_training_resume(root, completed['id'])
                    profile = {'system': 'Darwin', 'machine': 'arm64', 'metal_available': True,
                               'metal_device': {}, 'available_memory_bytes': 1, 'free_disk_bytes': 1, 'errors': []}
                    with patch.object(training.hardware, 'hardware', return_value=profile):
                        blocked = budget.review_training_resume(root, parent['id'])
                    self.assertFalse(blocked['feasible'])
                    self.assertTrue(blocked['blockers'])
                    self.assertFalse(blocked['training_approved'])
