import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import studio


class LabelReviewTest(unittest.TestCase):
    def test_review_flags_uncertain_text_without_relabeling_or_exclusion(self):
        rows = [{'text': f'Independent example {index}', 'label': 'fruit', 'group': str(index)} for index in range(6)]
        job = {'id': 'review-fixture', 'recipe': 'classifier', 'plan': {'labels': ['fruit', 'astronomy']}, 'status': 'reviewing_labels'}
        def ask(_, data):
            return {'reviews': [{'index': item['index'], 'ambiguous': item['text'].endswith('5'),
                'reason': 'Insufficient context.' if item['text'].endswith('5') else ''} for item in reversed(data['examples'])]}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'ask', side_effect=ask) as model, patch.object(studio, 'store_job'):
            studio.TRAINING_DATA[job['id']] = rows
            studio.review_dataset_labels(job)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(job['status'], 'dataset_ready')
        self.assertEqual((job['label_reviewed_rows'], job['label_review_flags']), (6, 1))
        self.assertEqual(job['preview'][0]['text'], 'Independent example 5')
        self.assertEqual(job['preview'][0]['label_review']['reason'], 'Insufficient context.')
        self.assertEqual(job['usable_counts']['fruit'], 6)
        self.assertEqual([row['label'] for row in studio.TRAINING_DATA.pop(job['id'])], ['fruit'] * 6)
        self.assertTrue(all('label_review' not in row for row in rows))

    def test_failed_later_batch_preserves_dataset_and_training_approval(self):
        rows = [{'text': f'Example {index}', 'label': 'fruit', 'group': str(index)} for index in range(5)]
        job = {'id': 'failed-review', 'recipe': 'classifier', 'plan': {'labels': ['fruit', 'astronomy']}}
        responses = [{'reviews': [{'index': index, 'ambiguous': False, 'reason': ''} for index in range(4)]}, {'reviews': [{'index': 99, 'ambiguous': True, 'reason': 'Invalid index'}]}]
        with patch.object(studio, 'ask', side_effect=responses), patch.object(studio, 'store_job'):
            studio.TRAINING_DATA[job['id']] = rows
            studio.review_dataset_labels(job)
        self.assertIs(studio.TRAINING_DATA.pop(job['id']), rows)
        self.assertTrue(all('label_review' not in row for row in rows))
        self.assertEqual(job['status'], 'dataset_ready')
        self.assertIn('invalid suggestion', job['error'])

    def test_interrupted_review_reopens_saved_dataset_for_approval(self):
        import json
        job_id = 'a' * 32
        rows = [{'text': 'Saved dataset example', 'label': 'fruit', 'group': 'A'}]
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)):
            work = Path(folder) / 'training-sessions' / job_id
            work.mkdir(parents=True)
            (work / 'dataset.json').write_text(json.dumps(rows))
            job = {'id': job_id, 'status': 'reviewing_labels', 'recipe': 'classifier'}
            (work.parent / (job_id + '.json')).write_text(json.dumps(job))
            studio.restore_jobs()
            self.assertEqual(studio.JOBS[job_id]['status'], 'dataset_ready')
            self.assertIn('review was interrupted', studio.JOBS[job_id]['error'])
            self.assertEqual(studio.TRAINING_DATA[job_id], rows)
            studio.JOBS.pop(job_id)
            studio.TRAINING_DATA.pop(job_id)
