from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials


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
