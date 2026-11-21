import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_continuations as continuation, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class PartialResumeBudgetTest(unittest.TestCase):
    def test_unknown_order_rejected_before_resource_review(self):
        partial = {'review': {'source': {'record_id': 'unused'}}}
        with patch.object(continuation, 'read', return_value=partial), patch.object(training, 'read', return_value={'review': {'config': {'schema_version': 10}}}), patch.object(isolated, 'review_partial') as review:
            with self.assertRaises(ValueError):
                budget.review_partial(Path('/unused'), 'unused')
            review.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real canceled continuation and isolated recovery')
    def test_retained_counter_controls_new_work_and_calibration(self):
        for kind in ('sgd', 'adamw'):
            for executed in (0, 3):
                with self.subTest(optimizer=kind, executed=executed), TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source, saved, base = corpus(root)
                    config = {**base, 'optimizer': kind, 'batch_size': 2, 'gradient_accumulation_steps': 2,
                              'weight_decay': .01 if kind == 'adamw' else 0.}
                    parent = training.run(root, True, source, saved, config, training.review(root, source, saved, config))
                    token = uuid.uuid4().hex
                    original = training.optimizer.update
                    calls = 0
                    if executed == 0:
                        continuation.cancellation.request(root, parent['id'], token, True)
                    def stop(*args):
                        nonlocal calls
                        value = original(*args)
                        calls += 1
                        if calls == executed:
                            continuation.cancellation.request(root, parent['id'], token, True)
                        return value
                    with patch.object(training.optimizer, 'update', side_effect=stop):
                        partial = continuation.run(root, parent['id'], True, continuation.review(root, parent['id']), token)
                    retained = 10 + executed
                    self.assertEqual(partial['status'], 'canceled')
                    self.assertEqual(partial['completed_steps'], retained)
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    proposal = budget.review_partial(root, partial['id'])
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    self.assertFalse(proposal['training_approved'])
                    self.assertFalse(proposal['release_approved'])
                    self.assertEqual(proposal['resume_from']['record_revision'], partial['revision'])
                    e = proposal['exposure']
                    self.assertEqual(e['restore_step'], retained)
                    self.assertEqual(e['optimizer_updates'], 20 - retained)
                    expected = sum(row['target_tokens'] for row in parent['step_log'][retained:])
                    self.assertEqual(e['recorded_training_target_tokens'], expected)
                    self.assertEqual(e['full_workflow_optimizer_target_tokens'], expected)
                    self.assertEqual(e['comparison_reference_target_tokens'], 0)
                    self.assertIsNone(proposal['workflow_duration_estimate'])
                    with self.assertRaises(ValueError):
                        isolated.run_partial(root, partial['id'], True, proposal, uuid.uuid4().hex)
                    with self.assertRaises(ValueError):
                        isolated.run_partial(root, partial['id'], False, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                    completed = isolated.run_partial(root, partial['id'], True, proposal['resource_review'], uuid.uuid4().hex)
                    self.assertEqual(completed['restored_step'], retained)
                    self.assertEqual(completed['completed_steps'], 20)
                    self.assertEqual(sum(row['target_tokens'] for row in completed['step_log']), expected)
                    self.assertEqual(completed['lineage_depth'], 2)
                    self.assertLessEqual(completed['reference_parameter_max_error'], 1e-7)
                    work = budget.review_partial(root, partial['id'])['workflow_duration_estimate']
                    self.assertIsNotNone(work)
                    self.assertFalse(work['measured'])
                    self.assertTrue(any(row['record_id'] == completed['id'] for row in work['source_records']))
                    self.assertTrue(all(p.read_bytes() == value for p, value in before.items()))
                    with self.assertRaises(ValueError):
                        budget.review_partial(root, completed['id'])
                    profile = {'system': 'Darwin', 'machine': 'arm64', 'metal_available': True,
                               'metal_device': {}, 'available_memory_bytes': 1, 'free_disk_bytes': 1, 'errors': []}
                    with patch.object(training.hardware, 'hardware', return_value=profile):
                        blocked = budget.review_partial(root, partial['id'])
                    self.assertFalse(blocked['feasible'])
                    self.assertTrue(blocked['blockers'])
