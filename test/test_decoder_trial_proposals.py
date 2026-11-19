from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials, decoder_datasets

def documents():
    words = ['amber', 'birch', 'cedar', 'dune']
    return [{'name': f'doc-{i}.txt', 'text': ' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]


class DecoderTrialProposalsTest(unittest.TestCase):
    def propose(self, root, approach='from_scratch'):
        return decoder_trials.propose(root, 'Try a tiny language model with new weights',
                                     Mock(return_value={'approach': approach, 'reason': 'Use the bounded generated-text trial.'}))

    def test_proposal_is_read_only_until_exact_revision_is_explicitly_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            root = Path(temporary)
            proposal = self.propose(root)
            self.assertTrue(proposal['executable'])
            self.assertEqual(decoder_trials.list_trials(root), [])
            submit = Mock()
            with self.assertRaises(ValueError):
                decoder_trials.start(root, False, submit, proposal_id=proposal['id'], proposal_revision=proposal['revision'])
            with self.assertRaisesRegex(ValueError, 'proposal changed'):
                decoder_trials.start(root, True, submit, proposal_id=proposal['id'], proposal_revision='changed')
            submit.assert_not_called()
            trial = decoder_trials.start(root, True, submit, proposal_id=proposal['id'], proposal_revision=proposal['revision'])
            self.assertEqual(trial['proposal'], proposal)
            self.assertEqual(trial['approval']['revision'], decoder_trials.approval_revision(trial))
            with patch.object(decoder_trials.decoder_training, 'run', return_value={'passed': True}):
                decoder_trials.execute(root, trial['id'])
            self.assertEqual(decoder_trials.read(root, trial['id'])['status'], 'complete')

    def test_unavailable_approaches_never_create_or_submit_trials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for approach in ('fine_tuning', 'distillation', 'retrieval'):
                proposal = self.propose(root, approach)
                self.assertFalse(proposal['executable'])
                submit = Mock()
                with self.assertRaisesRegex(ValueError, 'cannot execute'):
                    decoder_trials.start(root, True, submit, proposal_id=proposal['id'], proposal_revision=proposal['revision'])
                submit.assert_not_called()
            self.assertEqual(decoder_trials.list_trials(root), [])

    def test_stale_implementation_and_invalid_model_output_fail_without_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proposal = self.propose(root)
            with patch.object(decoder_trials, 'specification', return_value={'changed': True}):
                with self.assertRaises(ValueError):
                    decoder_trials.start(root, True, Mock(), proposal_id=proposal['id'], proposal_revision=proposal['revision'])
            for result in (None, [], {'approach': 'unknown', 'reason': 'Invalid'}, {'approach': 'from_scratch', 'reason': ''}):
                with self.assertRaises(ValueError):
                    decoder_trials.propose(root, 'Trial goal', Mock(return_value=result))
            planner = Mock()
            for goal in (' ', 'x' * 3001, None):
                with self.assertRaises(ValueError): decoder_trials.propose(root, goal, planner)
            planner.assert_not_called()
            self.assertEqual(decoder_trials.list_trials(root), [])

    def test_capability_change_during_planning_invalidates_proposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(decoder_trials, 'specification', side_effect=[{'version': 1}, {'version': 2}]):
                with self.assertRaisesRegex(ValueError, 'changed while planning'):
                    self.propose(root)
            self.assertFalse((root / 'decoder-trial-proposals').exists())

    def test_dataset_proposal_binds_review_and_never_sends_document_text(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(decoder_trials, '_ACTIVE', set()), patch.object(decoder_trials, '_CANCEL', {}):
            root = Path(temporary)
            dataset = decoder_datasets.prepare(root, documents(), True)
            planner = Mock(return_value={'approach': 'from_scratch', 'reason': 'Use the reviewed splits.'})
            proposal = decoder_trials.propose(root, 'Learn this local corpus', planner, dataset=dataset)
            self.assertEqual(proposal['dataset_summary']['splits'], dataset['splits'])
            self.assertNotIn('amber', str(planner.call_args))
            self.assertEqual(decoder_trials.list_trials(root), [])
            submit = Mock()
            for selected in (None, decoder_datasets.prepare(root, documents(), True)):
                with self.assertRaises(ValueError):
                    decoder_trials.start(root, True, submit, proposal_id=proposal['id'], proposal_revision=proposal['revision'], dataset=selected)
            submit.assert_not_called()
            record = decoder_trials.start(root, True, submit, proposal_id=proposal['id'], proposal_revision=proposal['revision'], dataset=dataset)
            self.assertEqual(record['dataset'], dataset)
            self.assertEqual(record['proposal'], proposal)
            with patch.object(decoder_trials.decoder_dataset_training, 'run', return_value={'passed': True}) as train:
                decoder_trials.execute(root, record['id'])
            train.assert_called_once()

    def test_dataset_change_during_planning_rejects_proposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = decoder_datasets.prepare(root, documents(), True)
            def planner(*args):
                (root/'decoder-datasets'/dataset['id']/'documents.jsonl').write_text('{}')
                return {'approach': 'from_scratch', 'reason': 'Trial'}
            with self.assertRaises(ValueError):
                decoder_trials.propose(root, 'Learn corpus', planner, dataset=dataset)
            self.assertFalse((root/'decoder-trial-proposals').exists())
