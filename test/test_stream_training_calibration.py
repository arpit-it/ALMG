from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_training as training,decoder_stream_training_feasibility as feasibility,decoder_stream_training_measurements as measurements
from backend.run_manifest import digest
import test_stream_training as training_tests


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual measured Metal chunks')
class StreamTrainingCalibrationTests(unittest.TestCase):
    def fixture(self,root):
        record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
        initial=feasibility.review(root,record['id'],True,review)
        state=feasibility.begin(root,record['id'],True,review,initial)
        state=feasibility.step(root,state['id'],True,state['revision'])
        return record,review,initial,state

    def test_measured_chunks_raise_admission_readonly_and_can_block_previously_calculated_fit(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,review,initial,state=self.fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            calibrated=feasibility.review(root,record['id'],True,review);estimate=calibrated['estimates'];cal=calibrated['calibration']
            self.assertEqual(cal['compatible_chunk_count'],1)
            self.assertGreaterEqual(estimate['calibrated_gpu_working_bytes'],cal['observed_metal_peak_bytes'])
            self.assertGreater(estimate['required_available_memory_bytes'],initial['estimates']['required_available_memory_bytes'])
            self.assertEqual(set(before),{p for p in root.rglob('*') if p.is_file()});self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))
            low=deepcopy(calibrated['hardware']);low['available_memory_bytes']=(estimate['required_available_memory_bytes']+initial['estimates']['required_available_memory_bytes'])//2
            with patch.object(feasibility.hardware,'hardware',return_value=low),patch.object(training,'begin') as begin:
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.begin(root,record['id'],True,review,calibrated)
                begin.assert_not_called()
            with patch.object(training,'begin') as begin:
                with self.assertRaises(ValueError):feasibility.begin(root,record['id'],True,review,initial)
                begin.assert_not_called()

    def test_runtime_or_producer_mismatch_does_not_calibrate_but_history_remains_readable(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,review,initial,state=self.fixture(root)
            incompatible=feasibility.hardware.hardware(root);incompatible['mlx_version']='different'
            with patch.object(feasibility.hardware,'hardware',return_value=incompatible):self.assertEqual(feasibility.review(root,record['id'],True,review)['calibration']['compatible_chunk_count'],0)
            saved=measurements.read(root,state['id'],True)['records'][0];saved['implementation_sha256']='old-producer'
            saved['revision']=digest({k:v for k,v in saved.items() if k!='revision'})
            path=training._folder(root,state['id'])/'continuation-measurements'/(saved['after_revision']+'.json');path.write_text(json.dumps(saved))
            self.assertEqual(len(measurements.read(root,state['id'],True)['records']),1)
            self.assertEqual(feasibility.review(root,record['id'],True,review)['calibration']['compatible_chunk_count'],0)
