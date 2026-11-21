import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class DurationEvidenceTest(unittest.TestCase):
    def test_invalid_counts_and_ignored_evidence_policies_are_rejected_early(self):
        with patch.object(training, '_source') as source:
            for count in (None,True,0,-1,21,1.5,'2'):
                with self.assertRaises(ValueError):
                    budget.review_limit(Path('/unused'),None,None,None,max_estimated_workflow_seconds=1000,minimum_duration_samples=count)
            with self.assertRaises(ValueError):
                budget.review_limit(Path('/unused'),None,None,None,1000,minimum_duration_samples=2)
            source.assert_not_called()

    def test_absent_evidence_remains_ineligible_without_changing_legacy_token_planning(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'at least 2 compatible'):
                budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
            legacy=budget.review_limit(root,source,saved,config,100000)
            self.assertEqual(legacy['selected_config']['steps'],20)
            self.assertEqual(legacy['minimum_duration_samples'],1)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real repeated compatible worker observations')
    def test_only_repeated_exact_budget_fresh_trials_satisfy_the_sample_filter(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved,base=corpus(root)
                config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                first={}
                for steps in (10,20):
                    c={**config,'steps':steps}
                    first[steps]=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
                default=budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000)
                self.assertEqual(default['selected_config']['steps'],20)
                with self.assertRaises(ValueError):
                    budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
                small={**config,'steps':10}
                training.run(root,True,source,saved,small,training.review(root,source,saved,small))
                with self.assertRaises(ValueError):
                    budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                second=isolated.run(root,True,source,saved,small,isolated.review(root,source,saved,small),uuid.uuid4().hex)
                after={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                proposal=budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
                self.assertEqual(proposal['selected_config']['steps'],10)
                counts={c['config']['steps']:c for c in proposal['considered_budgets']}
                self.assertEqual(counts[10]['compatible_duration_sample_count'],2)
                self.assertTrue(counts[10]['within_limit'])
                self.assertEqual(counts[20]['compatible_duration_sample_count'],1)
                self.assertFalse(counts[20]['within_limit'])
                work=proposal['selected_budget_review']['workflow_duration_estimate']
                self.assertEqual({s['record_id'] for s in work['source_records']},{first[10]['id'],second['id']})
                self.assertFalse(proposal['training_approved']);self.assertFalse(proposal['release_approved'])
                with self.assertRaises(ValueError):
                    budget.review_limit(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=3)
                self.assertEqual(after,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
