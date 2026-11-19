"""Synthetic readiness transitions, waiting and actual checkpoint preservation."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials, decoder_training

READY = {'ready': True, 'ac_power': True, 'idle_seconds': 600}


class DecoderReadinessTest(unittest.TestCase):
    def start(self, root, submit, trial_id=None, **options):
        with patch.object(decoder_trials.threading, 'Thread'):
            return decoder_trials.start(root, True, submit, trial_id, **options)

    def setUp(self):
        for name in ('_ACTIVE', '_CANCEL', '_READINESS'):
            patcher = patch.object(decoder_trials, name, set() if name == '_ACTIVE' else {})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_guard_waits_without_occupying_worker_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            with self.assertRaises(ValueError):
                self.start(root, submit, require_idle_ac=True)
            for state in (None, {**READY, 'ac_power': False}, {**READY, 'idle_seconds': 599},
                          {**READY, 'idle_seconds': float('nan')}):
                probe = Mock(return_value=state)
                with self.assertRaises(decoder_trials.ReadinessPaused):
                    decoder_trials.require_readiness(probe)
                record = self.start(root, submit, require_idle_ac=True, readiness=probe)
                self.assertEqual(record['status'], 'waiting_idle')
                event = decoder_trials._CANCEL[(str(root), record['id'])]
                with patch.object(event, 'wait', return_value=True):
                    decoder_trials.wait_and_submit(root, record['id'], submit)
                self.assertEqual(decoder_trials.read(root, record['id'])['status'], 'interrupted')
            submit.assert_not_called()

    def test_cancel_waiting_and_restart_never_start_training_implicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            record = self.start(root, submit, require_idle_ac=True, readiness=lambda: READY)
            decoder_trials.cancel(root, record['id'], True)
            decoder_trials.wait_and_submit(root, record['id'], submit)
            self.assertEqual(decoder_trials.read(root, record['id'])['interruption_reason'], 'user_cancelled')
            waiting = self.start(root, submit, require_idle_ac=True, readiness=lambda: READY)
            decoder_trials._ACTIVE.clear()
            decoder_trials.recover(root)
            self.assertEqual(decoder_trials.read(root, waiting['id'])['status'], 'interrupted')
            submit.assert_not_called()

    def test_guard_is_bound_to_approval_and_worker_failure_is_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = self.start(root, Mock(), require_idle_ac=True, readiness=lambda: READY)
            original = record['approval']['revision']
            record['scheduling']['require_idle_ac'] = False
            self.assertNotEqual(decoder_trials.approval_revision(record), original)
            decoder_trials.write(root, record)
            with patch.object(decoder_training, 'run') as train:
                decoder_trials.execute(root, record['id'])
                train.assert_not_called()
            waiting = self.start(root, Mock(), require_idle_ac=True, readiness=lambda: READY)
            decoder_trials.wait_and_submit(root, waiting['id'], Mock(side_effect=RuntimeError('Worker unavailable')))
            self.assertEqual(decoder_trials.read(root, waiting['id'])['interruption_reason'], 'worker_unavailable')
            self.assertNotIn((str(root), waiting['id']), decoder_trials._ACTIVE)

    def test_boundary_loss_interrupts_and_resume_cannot_remove_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            probe = Mock(side_effect=[READY, {**READY, 'ready': False}])
            record = self.start(root, submit, require_idle_ac=True, readiness=probe)
            decoder_trials.wait_and_submit(root, record['id'], submit)
            def train(*args, **kwargs):
                kwargs['stop']()
                self.fail('Readiness loss must interrupt')
            with patch.object(decoder_training, 'run', side_effect=train):
                decoder_trials.execute(root, record['id'])
            paused = decoder_trials.read(root, record['id'])
            self.assertEqual(paused['interruption_reason'], 'readiness_changed')
            self.assertEqual(paused['status'], 'interrupted')
            self.assertFalse(decoder_trials._READINESS)
            with self.assertRaises(ValueError):
                self.start(root, submit, record['id'], require_idle_ac=False)
            renewed = self.start(root, submit, record['id'], readiness=lambda: READY)
            self.assertNotEqual(renewed['approval']['id'], record['approval']['id'])
            decoder_trials.wait_and_submit(root, record['id'], submit)
            with patch.object(decoder_training, 'run', return_value={'passed': True}):
                decoder_trials.execute(root, record['id'])
            self.assertEqual(decoder_trials.read(root, record['id'])['status'], 'complete')

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS') == '1', 'Actual Metal verification')
    def test_real_boundary_pause_preserves_checkpoint_and_explicit_resume_reuses_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submit = Mock()
            def probe():
                checkpoint_exists = any((root/'decoder-trials').glob('*/artifacts/step-50/manifest.json'))
                return {**READY, 'ready': not checkpoint_exists}
            record = self.start(root, submit, require_idle_ac=True, readiness=probe)
            decoder_trials.wait_and_submit(root, record['id'], submit)
            decoder_trials.execute(root, record['id'])
            paused = decoder_trials.read(root, record['id'])
            self.assertEqual(paused['interruption_reason'], 'readiness_changed')
            self.assertTrue((decoder_trials.folder(root, record['id'])/'artifacts/step-50/manifest.json').exists())
            self.start(root, submit, record['id'], readiness=lambda: READY)
            decoder_trials.wait_and_submit(root, record['id'], submit)
            decoder_trials.execute(root, record['id'])
            completed = decoder_trials.read(root, record['id'])
            self.assertEqual(completed['status'], 'complete')
            self.assertTrue(completed['result']['passed'])
            self.assertTrue(completed['result']['checkpoint']['reused_existing_checkpoint'])
