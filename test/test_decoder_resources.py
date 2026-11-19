"""Resource admission and worker-entry checks for bounded decoder trials."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials, decoder_training, training_resources as resources


class DecoderResourcesTest(unittest.TestCase):
    def setUp(self):
        for name in ('_ACTIVE', '_CANCEL', '_READINESS'):
            patcher = patch.object(decoder_trials, name, set() if name == '_ACTIVE' else {})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_low_memory_disk_and_unknown_resources_do_not_create_or_submit_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            for memory, disk in ((1, 1024*resources.MIB), (1024*resources.MIB, 1)):
                with patch.object(resources, 'available_memory', return_value=memory), patch.object(resources.shutil, 'disk_usage', return_value=SimpleNamespace(free=disk)):
                    with self.assertRaises(resources.ResourceUnavailable):
                        decoder_trials.start(root, True, submit)
            with patch.object(resources, 'available_memory', side_effect=OSError('Unknown')):
                with self.assertRaises(resources.ResourceUnavailable):
                    decoder_trials.start(root, True, submit)
            submit.assert_not_called()
            self.assertEqual(decoder_trials.list_trials(root), [])

    def test_resource_loss_after_waiting_interrupts_before_model_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            ready = lambda: {'ready': True, 'ac_power': True, 'idle_seconds': 600}
            with patch.object(decoder_trials.threading, 'Thread'):
                record = decoder_trials.start(root, True, submit, require_idle_ac=True, readiness=ready)
            checkpoint = decoder_trials.folder(root, record['id'])/'artifacts/step-50/preserved'
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b'checkpoint fixture')
            decoder_trials.wait_and_submit(root, record['id'], submit)
            with patch.object(resources, 'check_size', side_effect=resources.ResourceUnavailable('Low disk')), patch.object(decoder_training, 'run') as train:
                decoder_trials.execute(root, record['id'])
                train.assert_not_called()
            paused = decoder_trials.read(root, record['id'])
            self.assertEqual(paused['interruption_reason'], 'resources_unavailable')
            self.assertEqual(checkpoint.read_bytes(), b'checkpoint fixture')
            with patch.object(resources, 'check_size', side_effect=resources.ResourceUnavailable('Low memory')):
                with self.assertRaises(resources.ResourceUnavailable):
                    decoder_trials.start(root, True, submit, record['id'], readiness=ready)
            self.assertEqual(decoder_trials.read(root, record['id']), paused)

    def test_completed_trial_records_both_probes_and_budget_is_approval_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = {'available_memory_bytes': 1024*resources.MIB, 'free_disk_bytes': 1024*resources.MIB,
                        'estimated_memory_reserve_bytes': 256*resources.MIB+128000*8,
                        'estimated_disk_reserve_bytes': 64*resources.MIB+128000*4}
            with patch.object(resources, 'check_size', return_value=snapshot) as check, patch.object(decoder_training, 'run', return_value={'passed': True}):
                record = decoder_trials.start(root, True, Mock())
                decoder_trials.execute(root, record['id'])
                self.assertEqual(check.call_count, 2)
                check.assert_called_with(128000, root)
            completed = decoder_trials.read(root, record['id'])
            self.assertEqual([item['phase'] for item in completed['resource_checks']], ['admission', 'execution'])
            self.assertEqual(completed['status'], 'complete')
            completed['specification']['resource_budget']['encoded_data_bytes'] = 0
            self.assertNotEqual(decoder_trials.approval_revision(completed), completed['approval']['revision'])

    def test_data_budget_rejects_boolean_negative_and_non_integer(self):
        for value in (True, -1, 1.5, '128000'):
            with self.assertRaises(ValueError):
                resources.check_size(value, Path('/tmp'))

    def test_boundary_loss_records_failure_and_preserves_cancel_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            record = decoder_trials.start(root, True, submit)
            checkpoint = decoder_trials.folder(root, record['id'])/'artifacts/step-50/preserved'
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b'unchanged checkpoint')
            snapshot = record['resource_checks'][0]
            def train(*args, **kwargs):
                self.assertFalse(kwargs['stop']())
                self.assertFalse(kwargs['stop']())
                kwargs['stop']()
                self.fail('Low resources must stop optimization')
            with patch.object(resources, 'check_size', side_effect=[snapshot, snapshot, snapshot, resources.ResourceUnavailable('Memory reserve lost')]), patch.object(decoder_training, 'run', side_effect=train):
                decoder_trials.execute(root, record['id'])
            paused = decoder_trials.read(root, record['id'])
            self.assertEqual(paused['interruption_reason'], 'resources_unavailable')
            self.assertEqual(paused['resource_monitor']['successful_boundaries'], 2)
            self.assertIn('Memory reserve lost', paused['resource_monitor']['last_failure']['error'])
            self.assertEqual(checkpoint.read_bytes(), b'unchanged checkpoint')
            self.assertEqual(len(paused['resource_checks']), 2)

    def test_boundary_evidence_merge_keeps_concurrent_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = decoder_trials.start(root, True, Mock())
            def probe(*args):
                decoder_trials.cancel(root, record['id'], True)
                return record['resource_checks'][0]
            with patch.object(resources, 'check_size', side_effect=probe):
                decoder_trials.monitor_resources(root, record['id'], record['specification'])
            saved = decoder_trials.read(root, record['id'])
            self.assertTrue(saved['cancel_requested'])
            self.assertEqual(saved['resource_monitor']['successful_boundaries'], 1)
