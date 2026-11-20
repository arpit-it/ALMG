import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_stream_duration as duration,decoder_stream_training as training,decoder_stream_training_feasibility as feasibility,decoder_stream_training_measurements as measurements
import test_stream_training as training_tests


def sample(step,seconds):
    return {'completed_steps':step,'measurements':{'request_work_seconds':seconds,'includes_final_heldout_evaluation':step==20}}


class StreamDurationTests(unittest.TestCase):
    def test_stage_maxima_include_final_evaluation_and_future_stages(self):
        records=[sample(5,5.),sample(5,7.),sample(10,11.),sample(15,13.),sample(20,29.)]
        model=duration.estimate(records,5)
        self.assertEqual(model['estimated_twenty_update_request_work_seconds'],60.)
        self.assertEqual(model['estimated_remaining_request_work_seconds'],53.)
        self.assertTrue(model['includes_final_evaluation'])
        updated=duration.estimate([sample(5,9.)],5,model)
        self.assertEqual(updated['estimated_twenty_update_request_work_seconds'],62.)
        self.assertEqual(updated['estimated_remaining_request_work_seconds'],53.)
        self.assertTrue(updated['borrowed_admission_stages'])

    def test_missing_final_stage_invalid_timings_and_completed_work(self):
        model=duration.estimate([sample(5,1.),sample(10,2.),sample(15,3.),sample(20,float('nan'))],10)
        self.assertIsNone(model['estimated_twenty_update_request_work_seconds'])
        self.assertIsNone(model['estimated_remaining_request_work_seconds'])
        self.assertFalse(model['includes_final_evaluation'])
        self.assertEqual(duration.estimate([],20)['estimated_remaining_request_work_seconds'],0)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual stage timing/evaluation')
    def test_completed_measured_trial_supplies_full_work_estimate_to_new_approval(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
            approved=feasibility.review(root,record['id'],True,review);self.assertIsNone(approved['estimates']['duration_estimate_seconds'])
            state=feasibility.begin(root,record['id'],True,review,approved)
            while state['status']!='complete':state=feasibility.step(root,state['id'],True,state['revision'])
            records=measurements.read(root,state['id'],True)['records']
            fresh=feasibility.review(root,record['id'],True,review);model=fresh['duration_estimate']
            self.assertEqual(model['estimated_twenty_update_request_work_seconds'],sum(r['measurements']['request_work_seconds'] for r in records))
            self.assertEqual(fresh['estimates']['duration_estimate_seconds'],model['estimated_twenty_update_request_work_seconds'])
            self.assertTrue(model['includes_final_evaluation']);self.assertEqual(len(model['stage_seconds']),4)
