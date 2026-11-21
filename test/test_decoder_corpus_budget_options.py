import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class BudgetOptionsTest(unittest.TestCase):
    def test_excluded_tokens_have_reasons_without_inventing_skipped_reviews(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(budget,'review',wraps=budget.review) as review:
                report=budget.review_options(root,source,saved,config,1,max_estimated_workflow_seconds=1000)
                review.assert_not_called()
            self.assertFalse(report['selection_available']);self.assertFalse(report['feasible'])
            self.assertIsNone(report['selected_config']);self.assertIsNone(report['selected_budget_review'])
            self.assertEqual(report['source'],saved['review']['source'])
            for candidate in report['considered_budgets']:
                self.assertEqual({r['kind'] for r in candidate['limit_blockers']},{'target_limit'})
                self.assertFalse(candidate['resource_review_checked'])
                self.assertFalse(candidate['duration_evidence_checked'])
                self.assertIsNone(candidate['admission_feasible'])
            with self.assertRaises(ValueError):budget.review_limit(root,source,saved,config,1)
            with self.assertRaises(ValueError):budget.review_options(root,source,saved,config,0)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_missing_timing_reserve_and_hardware_failures_stay_distinct_and_read_only(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            missing=budget.review_options(root,source,saved,config,max_estimated_workflow_seconds=1000)
            self.assertTrue(all(c['limit_blockers'][0]['kind']=='missing_duration_evidence' for c in missing['considered_budgets']))
            reserve=budget.review_options(root,source,saved,config,max_required_available_memory_bytes=1)
            self.assertTrue(all(any(r['kind']=='reserve_limit' and r['actual']>r['maximum'] for r in c['limit_blockers']) for c in reserve['considered_budgets']))
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                hardware=budget.review_options(root,source,saved,config,100000)
            self.assertTrue(hardware['selection_available']);self.assertFalse(hardware['feasible'])
            self.assertTrue(hardware['blockers'])
            self.assertTrue(all(c['limit_blockers']==[] and c['admission_feasible'] is False and c['admission_blockers'] for c in hardware['considered_budgets']))
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual compatible timing evidence and independent approval')
    def test_insufficient_samples_are_explained_and_become_eligible_only_after_real_repeat(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved,base=corpus(root)
                config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.};small={**config,'steps':10}
                first=isolated.run(root,True,source,saved,small,isolated.review(root,source,saved,small),uuid.uuid4().hex)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                report=budget.review_options(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
                reasons={c['config']['steps']:{r['kind'] for r in c['limit_blockers']} for c in report['considered_budgets']}
                self.assertEqual(reasons[10],{'insufficient_duration_samples'});self.assertEqual(reasons[20],{'missing_duration_evidence'})
                self.assertFalse(report['selection_available']);self.assertFalse(report['training_approved'])
                with self.assertRaises(ValueError):isolated.run(root,True,source,saved,small,report,uuid.uuid4().hex)
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                second=isolated.run(root,True,source,saved,small,isolated.review(root,source,saved,small),uuid.uuid4().hex)
                after={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                updated=budget.review_options(root,source,saved,config,max_estimated_workflow_seconds=1000,minimum_duration_samples=2)
                self.assertTrue(updated['selection_available']);self.assertEqual(updated['selected_config']['steps'],10)
                self.assertTrue(updated['feasible']);self.assertFalse(updated['training_approved']);self.assertFalse(updated['release_approved'])
                self.assertEqual(updated['considered_budgets'][0]['limit_blockers'],[])
                self.assertEqual({s['record_id'] for s in updated['selected_budget_review']['workflow_duration_estimate']['source_records']},{first['id'],second['id']})
                self.assertEqual(after,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
