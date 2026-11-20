import unittest
from unittest.mock import Mock
from backend.decoder_diagnostic_measurements import DiagnosticMeasurements


class DiagnosticMeasurementTests(unittest.TestCase):
    def test_samples_compare_against_estimate_without_resetting_shared_counters(self):
        mx=Mock();mx.get_active_memory.side_effect=[100,160,150];mx.get_peak_memory.side_effect=[900,950]
        measurement=DiagnosticMeasurements(mx,clock=Mock(side_effect=[5.,7.5]))
        measurement.sample('backward');result=measurement.finish(40)
        self.assertEqual(result['elapsed_seconds'],2.5)
        self.assertEqual(result['sampled_incremental_metal_bytes'],60)
        self.assertEqual(result['conservative_observed_gpu_budget_bytes'],60)
        self.assertTrue(result['observed_increment_exceeds_estimate'])
        self.assertEqual(result['process_peak_before_bytes'],900)
        self.assertEqual(result['process_peak_after_bytes'],950)
        self.assertFalse(result['isolated_trial_peak_measured'])
        self.assertIsNone(result['full_training_duration_seconds'])
        mx.reset_peak_memory.assert_not_called();self.assertEqual(mx.synchronize.call_count,3)

    def test_lower_sample_does_not_weaken_estimate_or_make_negative_increment(self):
        mx=Mock();mx.get_active_memory.side_effect=[200,100];mx.get_peak_memory.return_value=1000
        result=DiagnosticMeasurements(mx).finish(500)
        self.assertEqual(result['sampled_incremental_metal_bytes'],0)
        self.assertEqual(result['conservative_observed_gpu_budget_bytes'],500)
        self.assertFalse(result['observed_increment_exceeds_estimate'])
