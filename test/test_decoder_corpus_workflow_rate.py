from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class WorkflowTargetRateTest(unittest.TestCase):
    def work(self):
        return {'measured': False, 'estimated_seconds': 5., 'source_records': [
            {'record_id': 'one', 'record_revision': 'a', 'elapsed_seconds': 2.},
            {'record_id': 'two', 'record_revision': 'b', 'elapsed_seconds': 4.}],
            'limitations': 'Exact compatible workflow measurements only.'}

    def test_total_new_targets_use_workflow_timing_and_preserve_observed_range(self):
        work = self.work()
        before = deepcopy(work)
        result = budget.workflow_target_rate({'full_workflow_optimizer_target_tokens': 400}, work)
        self.assertFalse(result['measured'])
        self.assertEqual(result['estimated_workflow_optimizer_targets_per_second'], 80.)
        self.assertEqual(result['observed_min_workflow_optimizer_targets_per_second'], 100.)
        self.assertEqual(result['observed_max_workflow_optimizer_targets_per_second'], 200.)
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['source_records'][0]['record_id'], 'one')
        self.assertEqual(work, before)

    def test_reference_and_remaining_work_change_counts_without_imputing_kernel_speed(self):
        for targets in (502, 125, 114, 414, 87):
            result = budget.workflow_target_rate({'full_workflow_optimizer_target_tokens': targets}, self.work())
            self.assertEqual(result['estimated_workflow_optimizer_targets_per_second'], targets / 5.)
            self.assertFalse(result['measured'])
        for targets in (0, -1, True, 1.5):
            self.assertIsNone(budget.workflow_target_rate({'full_workflow_optimizer_target_tokens': targets}, self.work()))

    def test_missing_invalid_or_nonfinite_observations_produce_no_rate(self):
        exposure = {'full_workflow_optimizer_target_tokens': 400}
        for work in (None, {}, {'measured': True}, {**self.work(), 'source_records': []},
                     {**self.work(), 'estimated_seconds': 1.}):
            self.assertIsNone(budget.workflow_target_rate(exposure, work))
        for value in (0., -1., True, float('nan'), float('inf'), '2'):
            for location in ('elapsed', 'estimate'):
                work = self.work()
                if location == 'elapsed':
                    work['source_records'][0]['elapsed_seconds'] = value
                else:
                    work['estimated_seconds'] = value
                self.assertIsNone(budget.workflow_target_rate(exposure, work))
        work = self.work()
        del work['source_records'][0]['record_revision']
        self.assertIsNone(budget.workflow_target_rate(exposure, work))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires actual completed fresh-worker timing')
    def test_real_trial_updates_rate_without_granting_approval_or_claiming_optimizer_timing(self):
        for kind in ('sgd', 'adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, saved, base = corpus(root)
                config = {**base, 'optimizer': kind, 'weight_decay': .01 if kind == 'adamw' else 0.}
                first = budget.review(root, source, saved, config)
                self.assertIsNone(first['workflow_optimizer_target_rate_estimate'])
                result = isolated.run(root, True, source, saved, config, first['resource_review'], uuid.uuid4().hex)
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                proposal = budget.review(root, source, saved, config)
                rate = proposal['workflow_optimizer_target_rate_estimate']
                self.assertIsNotNone(rate)
                targets = 2 * sum(row['target_tokens'] for row in result['step_log'])
                self.assertEqual(rate['full_workflow_optimizer_target_tokens'], targets)
                sample = next(row for row in rate['source_records'] if row['record_id'] == result['id'])
                self.assertEqual(sample['workflow_optimizer_targets_per_second'], targets / result['isolated_workflow_measurements']['elapsed_seconds'])
                self.assertFalse(rate['measured'])
                self.assertIsNone(proposal['optimizer_only_tokens_per_second'])
                self.assertFalse(proposal['training_approved'])
                self.assertFalse(proposal['release_approved'])
                self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
