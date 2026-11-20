import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_training as training,decoder_stream_training_feasibility as feasibility,decoder_stream_training_measurements as measurements
import test_stream_training as training_tests


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real isolated Metal training')
class StreamChunkMeasurementTests(unittest.TestCase):
    def fixture(self,root):
        record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
        return feasibility.begin(root,record['id'],True,review,feasibility.review(root,record['id'],True,review))

    def test_isolated_chunks_measure_peaks_and_duration_excludes_final_evaluation(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);state=self.fixture(root);initial=state
            self.assertIsNone(measurements.read(root,state['id'],True)['estimated_remaining_update_checkpoint_seconds'])
            state=feasibility.step(root,state['id'],True,state['revision']);result=measurements.read(root,state['id'],True)
            self.assertEqual(len(result['records']),1);m=result['records'][0]['measurements']
            self.assertNotEqual(m['process_id'],os.getpid());self.assertTrue(m['isolated_process'])
            self.assertGreater(m['metal_peak_bytes'],0);self.assertGreater(m['process_peak_rss_bytes'],0)
            self.assertGreater(m['request_work_seconds'],m['elapsed_seconds'])
            self.assertEqual(result['estimated_remaining_update_checkpoint_seconds'],m['request_work_seconds']*3)
            self.assertEqual(feasibility.step(root,state['id'],True,initial['revision']),state)
            while state['status']!='complete':state=feasibility.step(root,state['id'],True,state['revision'])
            result=measurements.read(root,state['id'],True);self.assertEqual(len(result['records']),4)
            self.assertEqual(result['estimated_remaining_update_checkpoint_seconds'],0)
            self.assertTrue(result['records'][-1]['measurements']['includes_final_heldout_evaluation'])
            self.assertTrue(all(not r['measurements']['includes_final_heldout_evaluation'] for r in result['records'][:-1]))
            path=training._folder(root,state['id'])/'continuation-measurements'/(result['records'][0]['after_revision']+'.json')
            path.write_text(path.read_text().replace('almg-stream-chunk-measurements-v1','tampered'))
            self.assertEqual(len(measurements.read(root,state['id'],True)['records']),3)
            with self.assertRaises(ValueError):measurements.read(root,state['id'],False)

    def test_worker_errors_timeout_and_measurement_publication_do_not_lose_checkpoints(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);state=self.fixture(root)
            admission=feasibility.review(root,state['windows_id'],True,state['review'])
            with patch.object(feasibility,'review',return_value=admission),patch.object(measurements.subprocess,'run') as worker:
                for response in (subprocess.CompletedProcess([],1,json.dumps({'error':'fixture failure'})),subprocess.CompletedProcess([],0,'invalid'),subprocess.CompletedProcess([],0,'{}')):
                    worker.return_value=response
                    with self.assertRaises(ValueError):feasibility.step(root,state['id'],True,state['revision'])
                worker.side_effect=subprocess.TimeoutExpired('worker',120)
                with self.assertRaisesRegex(ValueError,'timed out'):feasibility.step(root,state['id'],True,state['revision'])
            self.assertEqual(training.read(root,state['id']),state)
            with patch.object(measurements,'_publish',side_effect=OSError('fixture disk failure')):
                with self.assertRaisesRegex(ValueError,'checkpoint is retained'):feasibility.step(root,state['id'],True,state['revision'])
            recovered=training.read(root,state['id']);self.assertEqual(recovered['completed_steps'],5)
            self.assertEqual(feasibility.step(root,state['id'],True,state['revision']),recovered)
