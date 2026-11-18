import tempfile
import unittest
from pathlib import Path
from backend import studio


def fixture_rows():
    return [{'text': f'{prefix} example token{index}', 'label': label, 'group': f'{label}-{index}'}
            for label, prefix in [('fruit', 'orchard apple harvest'), ('astronomy', 'telescope galaxy stars')]
            for index in range(24)]


class ClassifierCheckpointTest(unittest.TestCase):
    def test_resume_skips_completed_candidate_and_matches_uninterrupted_score(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'checkpoint.joblib'
            def interrupt(message):
                if 'candidate 2 of' in message:
                    raise RuntimeError('Fixture interruption')
            with self.assertRaisesRegex(RuntimeError, 'Fixture interruption'):
                studio.train(fixture_rows(), ['fruit', 'astronomy'], 0.8, report=interrupt, checkpoint_path=checkpoint)
            messages = []
            _, resumed_rows, resumed_metrics = studio.train(fixture_rows(), ['fruit', 'astronomy'], 0.8,
                report=messages.append, checkpoint_path=checkpoint)
            _, clean_rows, clean_metrics = studio.train(fixture_rows(), ['fruit', 'astronomy'], 0.8)
            self.assertTrue(any('Resuming 1 completed' in message for message in messages))
            self.assertFalse(any('Fitting and validating candidate 1 of' in message for message in messages))
            self.assertEqual(resumed_metrics, clean_metrics)
            self.assertEqual(resumed_rows, clean_rows)

    def test_changed_dataset_rejects_saved_candidate_state(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'checkpoint.joblib'
            studio.train(fixture_rows(), ['fruit', 'astronomy'], 0.8, checkpoint_path=checkpoint)
            changed = fixture_rows()
            changed[0]['text'] += ' changed'
            messages = []
            studio.train(changed, ['fruit', 'astronomy'], 0.8, checkpoint_path=checkpoint, report=messages.append)
            self.assertTrue(any('does not match' in message for message in messages))
            self.assertTrue(any('Fitting and validating candidate 1 of' in message for message in messages))

    def test_cancelled_dataset_requires_confirmation_and_stopped_worker(self):
        import json
        from unittest.mock import patch
        job = {'id': 'cancelled-fixture', 'status': 'cancelled', 'plan': {'labels': ['fruit', 'astronomy']}}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'TRAINING_WORKERS', set()):
            work = Path(folder) / 'training-sessions' / job['id']
            work.mkdir(parents=True)
            rows = fixture_rows()
            (work / 'dataset.json').write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, 'Confirm'):
                studio.cancelled_training_rows(job, False)
            studio.TRAINING_WORKERS.add(job['id'])
            with self.assertRaisesRegex(ValueError, 'still stopping'):
                studio.cancelled_training_rows(job, True)
            studio.TRAINING_WORKERS.clear()
            self.assertEqual(studio.cancelled_training_rows(job, True), rows)
            self.assertEqual(job['status'], 'cancelled')
            (work / 'dataset.json').write_text('[]')
            with self.assertRaisesRegex(ValueError, 'invalid'):
                studio.cancelled_training_rows(job, True)

    def test_training_worker_registration_clears_after_cancellation(self):
        from unittest.mock import patch
        job = {'id': 'worker-fixture', 'status': 'queued', 'idle': False, 'recipe': 'classifier',
               'target': 0.8, 'plan': {'labels': ['fruit', 'astronomy']}}
        with patch.object(studio, 'TRAINING_WORKERS', {job['id']}), patch.object(studio, 'TRAINING_DATA', {job['id']: fixture_rows()}), patch.object(studio, 'store_job'), patch.object(studio, 'train', side_effect=studio.TrainingCancelled):
            studio.run(job)
            self.assertNotIn(job['id'], studio.TRAINING_WORKERS)
