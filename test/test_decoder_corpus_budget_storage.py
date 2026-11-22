from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_budget as budget, decoder_corpus_isolated as isolated, decoder_corpus_storage_profile as storage
from test_decoder_corpus_optimizer import corpus


class BudgetStorageTest(unittest.TestCase):
    def test_missing_calibration_does_not_invent_zero_storage(self):
        for estimates in ({},{'corpus_work_estimate':None},{'corpus_work_estimate':{'source_records':[]}}):
            self.assertIsNone(budget.observed_storage(Path('.'),{'estimates':estimates}))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires exact completed fresh-worker storage observations')
    def test_completed_trial_updates_readonly_proposal_without_lowering_reserves(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root)
            self.assertIsNone(budget.review(root,source,saved,c)['observed_storage'])
            run=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=budget.review(root,source,saved,c);observed=report['observed_storage'];actual=storage.profile(root,run['id'])
            self.assertEqual(observed['complete_sample_count'],1)
            self.assertEqual(observed['observed_max_complete_total_bytes'],actual['total_bytes'])
            self.assertEqual(observed['source_records'][0]['record_id'],run['id'])
            self.assertIsNone(observed['estimated_future_bytes']);self.assertFalse(observed['admission_reserves_changed']);self.assertFalse(report['training_approved'])
            self.assertEqual(report['required_free_disk_bytes'],report['resource_review']['estimates']['required_free_disk_bytes'])
            self.assertIsNone(budget.review(root,source,saved,{**c,'steps':10})['observed_storage'])
            incompatible=deepcopy(report['resource_review']);incompatible['implementation_sha256']='other-producer'
            self.assertIsNone(budget.observed_storage(root,incompatible))
            stale=deepcopy(report['resource_review']);stale['estimates']['corpus_work_estimate']['source_records'][0]['record_revision']='stale'
            with self.assertRaises(ValueError):budget.observed_storage(root,stale)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            unknown=root/storage.interruptions.DIRECTORY/('f'*32);unknown.mkdir();(unknown/'record.json').write_text('{}')
            incomplete=budget.review(root,source,saved,c)['observed_storage']
            self.assertEqual(incomplete['complete_sample_count'],0);self.assertEqual(incomplete['incomplete_sample_count'],1)
            self.assertIsNone(incomplete['observed_max_complete_total_bytes'])
