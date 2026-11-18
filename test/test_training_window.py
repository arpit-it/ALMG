import unittest
from unittest.mock import patch
from backend import studio


class TrainingWindowTest(unittest.TestCase):
    def test_busy_device_waits_then_resumes_at_same_boundary(self):
        job = {'id': 'window-fixture', 'status': 'training', 'idle': True}
        rows = [{'text': 'fixture'}]
        with patch.object(studio, 'idle_ready', side_effect=[False, False, True]), patch.object(studio.time, 'sleep') as sleep, patch.object(studio, 'store_job'), patch.object(studio, 'activity') as activity, patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio.training_resources, 'check', return_value={'fixture': True}) as check:
            studio.wait_for_training_window(job)
        self.assertEqual(job['status'], 'training')
        self.assertEqual(sleep.call_count, 2)
        check.assert_called_once_with(rows, studio.ROOT)
        self.assertIn('paused between steps', activity.call_args_list[0].args[1])
        self.assertIn('Resuming training', activity.call_args_list[1].args[1])

    def test_cancelled_wait_never_resumes_or_runs_resource_probe(self):
        job = {'id': 'cancel-fixture', 'status': 'training', 'idle': True}
        def cancel(_): job['status'] = 'cancelled'
        with patch.object(studio, 'idle_ready', return_value=False), patch.object(studio.time, 'sleep', side_effect=cancel), patch.object(studio, 'store_job'), patch.object(studio, 'activity'), patch.object(studio.training_resources, 'check') as check:
            with self.assertRaises(studio.TrainingCancelled): studio.wait_for_training_window(job)
        self.assertEqual(job['status'], 'cancelled')
        check.assert_not_called()

    def test_immediate_training_does_not_probe_idle_or_power(self):
        with patch.object(studio, 'idle_ready') as probe:
            studio.wait_for_training_window({'idle': False})
        probe.assert_not_called()

    def test_macos_idle_and_power_gate_and_probe_failure(self):
        from unittest.mock import Mock
        import subprocess
        query = Mock(return_value=600.0)
        core_graphics = Mock(CGEventSourceSecondsSinceLastEventType=query)
        with patch.object(studio.sys, 'platform', 'darwin'), patch.object(studio.ctypes, 'CDLL', return_value=core_graphics), patch.object(studio.subprocess, 'check_output', return_value="Now drawing from 'AC Power'") as power:
            self.assertTrue(studio.idle_ready())
            query.return_value = 599.9
            self.assertFalse(studio.idle_ready())
            query.return_value = 900.0
            power.return_value = "Now drawing from 'Battery Power'"
            self.assertFalse(studio.idle_ready())
            power.side_effect = subprocess.TimeoutExpired('pmset', 3)
            self.assertFalse(studio.idle_ready())
