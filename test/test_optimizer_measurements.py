import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.decoder_optimizer_measurements import OptimizerMeasurements,process_peak_rss


class OptimizerMeasurementTests(unittest.TestCase):
    def test_shared_counters_and_sampled_memory_are_explicit_and_never_reset(self):
        mx=Mock();mx.get_active_memory.side_effect=[100,140,120];mx.get_peak_memory.side_effect=[900,900]
        observer=OptimizerMeasurements(mx,clock=Mock(side_effect=[1.,2.,3.]),rss=Mock(side_effect=[1000,1100,1200]))
        observer.sample('reference_update_1');observed=observer.finish()
        self.assertEqual(observed['elapsed_seconds'],2.);self.assertEqual(observed['sampled_active_metal_max_bytes'],140)
        self.assertEqual(observed['sampled_incremental_metal_bytes'],40);self.assertEqual(observed['shared_metal_peak_before_bytes'],900)
        self.assertEqual(observed['shared_metal_peak_after_bytes'],900);self.assertEqual(observed['baseline_process_peak_rss_bytes'],1000)
        self.assertEqual(observed['process_peak_rss_bytes'],1200);self.assertTrue(observed['measured'])
        self.assertFalse(observed['isolated_trial_peak_measured']);self.assertIsNone(observed['full_training_duration_seconds'])
        self.assertEqual([sample['phase'] for sample in observed['phase_samples']],['reference_update_1','finished'])
        mx.reset_peak_memory.assert_not_called();self.assertEqual(mx.synchronize.call_count,3)

    @unittest.skipUnless(os.name=='posix','RSS high-water counters require a POSIX host')
    def test_process_peak_rss_units_are_bytes_on_mac_and_linux(self):
        with patch('resource.getrusage',return_value=SimpleNamespace(ru_maxrss=2)):
            with patch('backend.decoder_optimizer_measurements.platform.system',return_value='Darwin'):self.assertEqual(process_peak_rss(),2)
            with patch('backend.decoder_optimizer_measurements.platform.system',return_value='Linux'):self.assertEqual(process_peak_rss(),2048)
