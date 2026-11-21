import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class ResourceLimitTest(unittest.TestCase):
    def test_invalid_reserve_ceilings_fail_before_source_access(self):
        with patch.object(training, '_source') as source:
            for key in ('max_required_available_memory_bytes','max_required_free_disk_bytes'):
                for value in (True,0,-1,1.5,'1000',2**63):
                    with self.assertRaises(ValueError):
                        budget.review_limit(Path('/unused'),None,None,None,100000,**{key:value})
            source.assert_not_called()

    def test_resource_only_exact_boundaries_denials_and_hardware_blockers_are_read_only(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            full=budget.review(root,source,saved,config)
            memory=full['required_available_memory_bytes'];disk=full['required_free_disk_bytes']
            for caps in ({'max_required_available_memory_bytes':memory}, {'max_required_free_disk_bytes':disk},
                         {'max_required_available_memory_bytes':memory,'max_required_free_disk_bytes':disk}):
                result=budget.review_limit(root,source,saved,config,**caps)
                self.assertEqual(result['selected_config']['steps'],20)
                self.assertTrue(all(c['resource_review_checked'] for c in result['considered_budgets']))
                self.assertFalse(result['training_approved']);self.assertFalse(result['release_approved'])
            for caps in ({'max_required_available_memory_bytes':1},{'max_required_free_disk_bytes':1}):
                with self.assertRaisesRegex(ValueError,'No supported update budget'):
                    budget.review_limit(root,source,saved,config,**caps)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                blocked=budget.review_limit(root,source,saved,config,max_required_available_memory_bytes=2**63-1,max_required_free_disk_bytes=2**63-1)
            self.assertFalse(blocked['feasible']);self.assertTrue(blocked['blockers'])
            small=budget.review(root,source,saved,{**config,'steps':10})['exposure']['recorded_training_target_tokens']
            combined=budget.review_limit(root,source,saved,config,None,small,max_required_available_memory_bytes=2**63-1,max_required_free_disk_bytes=2**63-1)
            self.assertEqual(combined['selected_config']['steps'],10)
            self.assertFalse(combined['considered_budgets'][1]['resource_review_checked'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual independently approved budget execution')
    def test_selected_reserves_fit_ceilings_and_action_approval_remains_bound(self):
        for kind in ('sgd','adamw'):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved,base=corpus(root)
                config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                full=budget.review(root,source,saved,config)
                proposal=budget.review_limit(root,source,saved,config,max_required_available_memory_bytes=full['required_available_memory_bytes'],max_required_free_disk_bytes=full['required_free_disk_bytes'])
                selected=proposal['selected_budget_review'];resource=selected['resource_review']
                self.assertLessEqual(selected['required_available_memory_bytes'],proposal['max_required_available_memory_bytes'])
                self.assertLessEqual(selected['required_free_disk_bytes'],proposal['max_required_free_disk_bytes'])
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                for settings,reviewed,confirmed in ((config,proposal,True),(config,resource,False),({**config,'steps':10},resource,True)):
                    with self.assertRaises(ValueError):
                        isolated.run(root,confirmed,source,saved,settings,reviewed,uuid.uuid4().hex)
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                actual=isolated.run(root,True,source,saved,proposal['selected_config'],resource,uuid.uuid4().hex)
                self.assertEqual(actual['completed_steps'],20)
                self.assertLessEqual(actual['checkpoint_parameter_max_error'],1e-7)
                self.assertLessEqual(actual['checkpoint_optimizer_max_error'],1e-7)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
