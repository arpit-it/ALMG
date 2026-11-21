import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class DurationLimitTest(unittest.TestCase):
    def test_invalid_duration_limits_fail_before_source_access(self):
        with patch.object(training, '_source') as source:
            for value in (True, 0, -1, '3', float('nan'), float('inf'), 2**200):
                with self.assertRaises(ValueError):
                    budget.review_limit(Path('/unused'), None, None, None, 1000, None, value)
            source.assert_not_called()

    def test_unknown_timing_cannot_pass_but_legacy_token_only_planning_still_works(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, config = corpus(root)
            before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'compatible completed timing'):
                budget.review_limit(root, source, saved, config, max_estimated_workflow_seconds=1000)
            legacy = budget.review_limit(root, source, saved, config, 100000)
            self.assertEqual(legacy['selected_config']['steps'], 20)
            self.assertTrue(all(not c['duration_evidence_checked'] for c in legacy['considered_budgets']))
            self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_token_rejections_do_not_trigger_unnecessary_duration_reviews(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source, saved, config = corpus(root)
            small = budget.review(root, source, saved, {**config,'steps':10})['exposure']['recorded_training_target_tokens']
            original = budget.review
            with patch.object(budget, 'review', wraps=original) as review:
                with self.assertRaises(ValueError):
                    budget.review_limit(root, source, saved, config, None, small, 1000)
                self.assertEqual([call.args[3]['steps'] for call in review.call_args_list], [10])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Requires real completed-worker duration samples')
    def test_real_timing_filters_candidates_and_selected_configuration_keeps_approval_binding(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind), TemporaryDirectory() as temporary:
                root = Path(temporary); source, saved, base = corpus(root)
                config = {**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                times = []
                for steps in (10,20):
                    c = {**config,'steps':steps}
                    isolated.run(root, True, source, saved, c, isolated.review(root, source, saved, c), uuid.uuid4().hex)
                    times.append(budget.review(root, source, saved, c)['workflow_duration_estimate']['estimated_seconds'])
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                result = budget.review_limit(root, source, saved, config, max_estimated_workflow_seconds=times[0])
                eligible = [c for c in result['considered_budgets'] if c['within_limit']]
                self.assertEqual(result['selected_config']['steps'], max(c['config']['steps'] for c in eligible))
                self.assertLessEqual(result['selected_budget_review']['workflow_duration_estimate']['estimated_seconds'], times[0])
                self.assertFalse(result['training_approved'])
                with self.assertRaises(ValueError):
                    budget.review_limit(root, source, saved, config, max_estimated_workflow_seconds=min(times)/2)
                with self.assertRaises(ValueError):
                    budget.review_limit(root, source, saved, {**config,'learning_rate':.005}, max_estimated_workflow_seconds=1000)
                small = budget.review(root, source, saved, {**config,'steps':10})['exposure']['recorded_training_target_tokens']
                selected = budget.review_limit(root, source, saved, config, None, small, max(times)*10)
                self.assertEqual(selected['selected_config']['steps'], 10)
                resource = selected['selected_budget_review']['resource_review']
                with self.assertRaises(ValueError):
                    isolated.run(root, True, source, saved, config, resource, uuid.uuid4().hex)
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                actual = isolated.run(root, True, source, saved, selected['selected_config'], resource, uuid.uuid4().hex)
                self.assertEqual(actual['completed_steps'], 10)
                self.assertLessEqual(actual['checkpoint_parameter_max_error'], 1e-7)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
