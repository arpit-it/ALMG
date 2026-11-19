from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials


class DecoderTrialsTest(unittest.TestCase):
    def test_approval_required_and_receipt_persists_before_worker_submission(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            submit = Mock()
            for confirmed in (None, False, 1):
                with self.assertRaises(ValueError): decoder_trials.start(root, confirmed, submit)
            self.assertEqual(list(root.iterdir()), [])
            record = decoder_trials.start(root, True, submit)
            restored = decoder_trials.read(root, record['id'])
            self.assertEqual(restored['status'], 'queued')
            self.assertEqual(restored['approval']['revision'], decoder_trials.run_manifest.digest(restored['specification']))
            self.assertEqual(restored['specification']['approach'], 'from_scratch')
            submit.assert_called_once_with(decoder_trials.execute, root, record['id'])

    def test_restart_requires_renewed_approval_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            record = decoder_trials.start(root, True, Mock())
            receipt = record['approval']
            checkpoint = decoder_trials.folder(root, record['id']) / 'artifacts' / 'step-50'
            checkpoint.mkdir(parents=True)
            (checkpoint / 'preserved').write_text('checkpoint fixture')
            decoder_trials._ACTIVE.clear()
            decoder_trials.recover(root)
            restored = decoder_trials.read(root, record['id'])
            self.assertEqual(restored['status'], 'interrupted')
            self.assertEqual(restored['approval'], receipt)
            with self.assertRaises(ValueError): decoder_trials.start(root, False, Mock(), record['id'])
            renewed = decoder_trials.start(root, True, Mock(), record['id'])
            self.assertNotEqual(renewed['approval']['id'], receipt['id'])
            self.assertEqual(renewed['previous_approvals'], [receipt])
            self.assertEqual((checkpoint / 'preserved').read_text(), 'checkpoint fixture')

    def test_changed_implementation_and_existing_bundle_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            record = decoder_trials.start(root, True, Mock())
            decoder_trials._ACTIVE.clear()
            decoder_trials.recover(root)
            with patch.object(decoder_trials, 'specification', return_value={'changed': True}):
                with self.assertRaisesRegex(ValueError, 'implementation changed'):
                    decoder_trials.start(root, True, Mock(), record['id'])
            bundle = decoder_trials.folder(root, record['id']) / 'artifacts' / 'bundle'
            bundle.mkdir(parents=True)
            (bundle / 'preserved').write_text('model fixture')
            with self.assertRaisesRegex(ValueError, 'complete bundle'):
                decoder_trials.start(root, True, Mock(), record['id'])
            self.assertEqual((bundle / 'preserved').read_text(), 'model fixture')

    def test_worker_records_result_and_restart_keeps_completed_trial(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            record = decoder_trials.start(root, True, Mock())
            with patch.object(decoder_trials.decoder_training, 'run', return_value={'passed': True}) as train:
                decoder_trials.execute(root, record['id'])
            restored = decoder_trials.read(root, record['id'])
            self.assertEqual(restored['status'], 'complete')
            self.assertTrue(restored['result']['passed'])
            train.assert_called_once_with(decoder_trials.recipe_contracts.initialize_recipe,
                work_directory=decoder_trials.folder(root, record['id']) / 'artifacts')
            decoder_trials.recover(root)
            self.assertEqual(decoder_trials.read(root, record['id']), restored)
            for trial_id in ('../escape', None, 'invalid'):
                with self.assertRaises(ValueError): decoder_trials.read(root, trial_id)

    def test_submission_and_training_failures_preserve_interrupted_record(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            with self.assertRaises(RuntimeError):
                decoder_trials.start(root, True, Mock(side_effect=RuntimeError('fixture')))
            record = decoder_trials.list_trials(root)[0]
            self.assertEqual(record['status'], 'interrupted')
            self.assertFalse(decoder_trials._ACTIVE)
            decoder_trials.start(root, True, Mock(), record['id'])
            with patch.object(decoder_trials.decoder_training, 'run', side_effect=ValueError('fixture failure')):
                decoder_trials.execute(root, record['id'])
            self.assertEqual(decoder_trials.read(root, record['id'])['error'], 'fixture failure')
            self.assertFalse(decoder_trials._ACTIVE)

    def test_changed_queued_revision_cannot_invoke_training(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()):
            root = Path(temporary)
            record = decoder_trials.start(root, True, Mock())
            record['approval']['revision'] = 'changed'
            decoder_trials.write(root, record)
            with patch.object(decoder_trials.decoder_training, 'run') as train:
                decoder_trials.execute(root, record['id'])
                train.assert_not_called()
            self.assertEqual(decoder_trials.read(root, record['id'])['status'], 'interrupted')
