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
