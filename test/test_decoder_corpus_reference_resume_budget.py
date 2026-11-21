import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class ReferenceResumeBudgetTest(unittest.TestCase):
    def test_reference_and_training_have_distinct_cursors_and_masked_counts(self):
        windows = [{'inputs': [0]*4, 'targets': [0]*4, 'target_mask': mask}
                   for mask in ([1, 1, 0, 0], [1, 0, 0, 0], [1, 1, 1, 0])]
        config = {'steps': 10, 'batch_size': 2, 'sequence_length': 4, 'gradient_accumulation_steps': 2}
        result = budget.reference_recovery_exposure(windows, config, 10, 5)
        self.assertEqual(result['recorded_training_target_tokens'], 39)
        self.assertEqual(result['comparison_reference_target_tokens'], 19)
        self.assertEqual(result['full_workflow_optimizer_target_tokens'], 58)
        self.assertEqual(result['full_workflow_optimizer_updates'], 15)
        self.assertEqual(result['full_workflow_dense_token_positions'], 120)
        self.assertEqual(result['comparison_reference_padding_target_positions'], 21)
        self.assertEqual(result['initial_window_offset'], 0)
        self.assertEqual(result['reference_initial_window_offset'], 1)
        self.assertEqual(result['training_tokens_per_parameter'], 3.9)
        zero = budget.reference_recovery_exposure(windows, config, 10, 0)
        self.assertEqual(zero['full_workflow_optimizer_target_tokens'], 78)
        finished = budget.reference_recovery_exposure(windows, config, 10, 10)
        self.assertEqual(finished['comparison_reference_target_tokens'], 0)
        self.assertEqual(finished['full_workflow_optimizer_target_tokens'], 39)
        for invalid in (True, -1, 11, 1.5):
            with self.assertRaises(ValueError):
                budget.reference_recovery_exposure(windows, config, 10, invalid)

    def test_unknown_order_rejected_before_resource_review(self):
        with patch.object(training, 'read', return_value={'review': {'config': {'schema_version': 10}}}), patch.object(isolated, 'review_reference_resume') as review:
            with self.assertRaises(ValueError):
                budget.review_reference_resume(Path('/unused'), 'unused')
            review.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real saved training-phase recovery')
    def test_reference_tail_and_complete_training_match_actual_recovery(self):
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
                        if calls == retained:
                            training.run_cancellation.request(root, approved, token, True)
                        return value
                    with patch.object(training.optimizer, 'update', side_effect=stop):
                        parent = training.run(root, True, source, saved, config, approved, request_id=token)
                    self.assertEqual(parent['cancellation_phase'], 'reference_verification')
                    self.assertEqual(parent['completed_steps'], retained)
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    proposal = budget.review_reference_resume(root, parent['id'])
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    self.assertFalse(proposal['training_approved'])
                    self.assertFalse(proposal['release_approved'])
                    e = proposal['exposure']
                    self.assertEqual(e['optimizer_updates'], 20)
                    self.assertEqual(e['reference_optimizer_updates'], 20 - retained)
                    self.assertEqual(e['full_workflow_optimizer_updates'], 40 - retained)
                    self.assertEqual(e['restore_step'], 0)
                    self.assertEqual(e['reference_restore_step'], retained)
                    self.assertIsNone(proposal['workflow_duration_estimate'])
                    with self.assertRaises(ValueError):
                        isolated.run_reference_resume(root, parent['id'], True, proposal, uuid.uuid4().hex)
                    with self.assertRaises(ValueError):
                        isolated.run_reference_resume(root, parent['id'], False, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    completed = isolated.run_reference_resume(root, parent['id'], True, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(completed['reference_steps_carried'], retained)
                    self.assertEqual(completed['reference_updates_executed'], 20 - retained)
                    self.assertEqual(len(completed['step_log']), 20)
                    self.assertEqual(completed['reference_step_log'][:retained], parent['reference_step_log'])
                    targets = sum(row['target_tokens'] for row in completed['step_log'])
                    reference_targets = sum(row['target_tokens'] for row in completed['reference_step_log'][retained:])
                    self.assertEqual(targets, e['recorded_training_target_tokens'])
                    self.assertEqual(reference_targets, e['comparison_reference_target_tokens'])
                    self.assertEqual(e['full_workflow_optimizer_target_tokens'], targets + reference_targets)
                    self.assertLessEqual(completed['checkpoint_parameter_max_error'], 1e-7)
                    self.assertLessEqual(completed['checkpoint_optimizer_max_error'], 1e-7)
                    work = budget.review_reference_resume(root, parent['id'])['workflow_duration_estimate']
                    self.assertIsNotNone(work)
                    self.assertFalse(work['measured'])
                    self.assertTrue(any(row['record_id'] == completed['id'] for row in work['source_records']))
                    self.assertTrue(all(p.read_bytes() == value for p, value in before.items()))
                    with self.assertRaises(ValueError):
                        budget.review_reference_resume(root, completed['id'])
                    profile = {'system': 'Darwin', 'machine': 'arm64', 'metal_available': True,
                               'metal_device': {}, 'available_memory_bytes': 1, 'free_disk_bytes': 1, 'errors': []}
                    with patch.object(training.hardware, 'hardware', return_value=profile):
                        blocked = budget.review_reference_resume(root, parent['id'])
                    self.assertFalse(blocked['feasible'])
                    self.assertTrue(blocked['blockers'])
                    self.assertFalse(blocked['training_approved'])
