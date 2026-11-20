from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_trial_feasibility as feasibility,decoder_trial_measurements as measurements,decoder_trials as trials


class DecoderTrialMeasurementTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real saved-trial Metal execution')
    def test_actual_completed_worker_feeds_same_scope_estimate_with_persistence_included(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);before=feasibility.review(root);self.assertIsNone(before['estimates']['worker_work_estimate']);queued=[]
            created=feasibility.start(root,True,lambda function,*args:queued.append((function,args)),before)
            function,args=queued.pop();function(*args);record=trials.read(root,created['id']);self.assertEqual(record['status'],'complete',record.get('error'))
            observation=record['worker_measurements'][0];self.assertTrue(observation['measured']);self.assertFalse(observation['peak_memory_measured']);self.assertGreater(observation['elapsed_seconds'],0)
            self.assertEqual(observation['started_checkpoint'],{'completed_steps':0,'files':{}})
            review=feasibility.review(root);estimate=review['estimates']['worker_work_estimate']
            self.assertEqual(estimate['sample_count'],1);self.assertGreater(estimate['estimated_seconds'],observation['elapsed_seconds']);self.assertFalse(estimate['measured'])
            self.assertEqual(estimate['source_measurements'][0]['measurement_id'],observation['id']);self.assertIsNone(review['estimates']['duration_estimate_seconds'])
            self.assertEqual(record['generated_trial_hardware']['approval'],before)
            path=trials.folder(root,record['id'])/'record.json';original=path.read_text()
            for field in ('runtime','implementation','checkpoint','outcome','approval','nonpositive','tampered'):
                changed=deepcopy(record);value=changed['worker_measurements'][0]
                if field=='runtime':value['runtime']['python']='other'
                elif field=='implementation':value['implementation_sha256']='other'
                elif field=='checkpoint':value['started_checkpoint']['completed_steps']=50
                elif field=='outcome':value['outcome']='interrupted'
                elif field=='approval':value['approval_id']='other'
                else:value['elapsed_seconds']=0
                if field!='tampered':value['revision']=measurements.digest({k:v for k,v in value.items() if k!='revision'})
                path.write_text(json.dumps(changed));self.assertIsNone(feasibility.review(root)['estimates']['worker_work_estimate'],field)
            path.write_text(original)
            # A step-50 resume must not inherit a full fresh-worker estimate.
            self.assertIsNone(measurements.estimate(root,review['specification_sha256'],review['hardware'],{'completed_steps':50,'files':{}}))

    def test_optional_timing_publication_failure_preserves_engine_result_and_completed_state(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);created=trials.start(root,True,lambda *args:None);key=(str(root),created['id'])
            def function(directory,identifier):
                record=trials.read(directory,identifier);record['status']='complete';record['result']={'sentinel':True};trials.write(directory,record);return 'engine-result'
            try:
                with patch.object(measurements,'_save_observation',side_effect=OSError('fixture disk failure')):
                    self.assertEqual(measurements.execute(function,root,created['id']),'engine-result')
                record=trials.read(root,created['id']);self.assertEqual(record['status'],'complete');self.assertEqual(record['result'],{'sentinel':True});self.assertNotIn('worker_measurements',record)
            finally:trials._ACTIVE.discard(key);trials._CANCEL.pop(key,None)
