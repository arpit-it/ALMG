import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_feedback as feedback, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class CorpusMetalFloorTest(unittest.TestCase):
    def test_floors_never_reduce_and_missing_peak_remains_unknown(self):
        estimates={'estimated_gpu_working_bytes':10,'calibrated_gpu_working_bytes':20,'required_available_memory_bytes':100}
        feedback.apply_memory_floor(estimates,{'calculated_memory_floor_bytes':80})
        self.assertIsNone(estimates['calculated_metal_working_floor_bytes']);self.assertEqual(estimates['calibrated_gpu_working_bytes'],20)
        feedback.apply_memory_floor(estimates,{'calculated_memory_floor_bytes':200,'isolated_metal_peak_bytes':21})
        self.assertEqual(estimates['calculated_metal_working_floor_bytes'],27);self.assertEqual(estimates['calibrated_gpu_working_bytes'],27);self.assertEqual(estimates['required_available_memory_bytes'],200)
        before=dict(estimates)
        feedback.apply_memory_floor(estimates,{'calculated_memory_floor_bytes':50,'isolated_metal_peak_bytes':8})
        feedback.apply_memory_floor(estimates,None);self.assertEqual(estimates,before)

    def test_metal_only_shortfall_blocks_worker_before_execution(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{'max_recommended_working_set_size':1000000},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            memory={'calculated_memory_floor_bytes':300000000,'isolated_metal_peak_bytes':2000000}
            with patch.object(training.hardware,'hardware',return_value=profile),patch.object(feedback,'feedback',return_value=(memory,None)),patch.object(isolated,'_execute') as execute:
                review=isolated.review(root,source,saved,c)
                self.assertFalse(review['feasible']);self.assertEqual(review['estimates']['calibrated_gpu_working_bytes'],2500000)
                self.assertTrue(training.hardware._fits(profile,{**review['estimates'],'calibrated_gpu_working_bytes':review['estimates']['estimated_gpu_working_bytes']}))
                self.assertTrue(any('Metal working-set' in reason for reason in review['blockers']))
                with self.assertRaises(ValueError):isolated.run(root,True,source,saved,c,review,uuid.uuid4().hex)
                execute.assert_not_called()
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual fresh and continuation Metal peak calibration')
    def test_real_fresh_and_continuation_peak_floors_are_reported_readonly(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root)
            run=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
            continued=isolated.run_continuation(root,run['id'],True,isolated.review_continuation(root,run['id']),uuid.uuid4().hex)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for review,key in ((isolated.review(root,source,saved,c),'isolated_corpus_memory'),(isolated.review_continuation(root,run['id']),'isolated_continuation_memory')):
                estimates=review['estimates'];memory=estimates[key];floor=math.ceil(memory['isolated_metal_peak_bytes']*1.25)
                self.assertEqual(estimates['calculated_metal_working_floor_bytes'],floor)
                self.assertGreaterEqual(estimates['calibrated_gpu_working_bytes'],max(floor,estimates['estimated_gpu_working_bytes']))
                self.assertTrue(review['feasible'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
