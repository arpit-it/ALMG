from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import inference, decoder_trials


class PlannerIdentityTest(unittest.TestCase):
    def test_loaded_identity_is_stable_and_tracks_verified_revision_without_mutation(self):
        stamp = {'version': 1, 'files': [{'name': 'weights.safetensors', 'size': 123, 'mtime_ns': 42}]}
        with patch.object(inference, '_loaded_stamp', stamp), patch.object(inference, '_model', object()):
            first = inference.loaded_identity()
            self.assertTrue(first['loaded'])
            self.assertEqual(first, inference.loaded_identity())
            self.assertEqual(len(first['verified_weights_revision']), 64)
            self.assertNotIn('files', first)
            stamp['files'][0]['mtime_ns'] = 43
            self.assertNotEqual(first['verified_weights_revision'], inference.loaded_identity()['verified_weights_revision'])
        with patch.object(inference, '_loaded_stamp', None), patch.object(inference, '_model', None):
            identity = inference.loaded_identity()
            self.assertFalse(identity['loaded'])
            self.assertIsNone(identity['verified_weights_revision'])

    def test_proposal_records_trusted_identity_after_generation_and_binds_it_to_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            order = []
            def planner(*args):
                order.append('generation')
                return {'recipe': 'decoder_from_scratch', 'approach': 'from_scratch', 'reason': 'Bounded local trial'}
            def identity():
                order.append('identity')
                return {'provider': 'local_qwen', 'model': 'fixture-model', 'loaded': True, 'verified_weights_revision': 'fixture-revision'}
            proposal = decoder_trials.propose(Path(temporary), 'Trial goal', planner, planner_identity=identity)
            self.assertEqual(order, ['generation', 'identity'])
            self.assertEqual(proposal['planner']['model'], 'fixture-model')
            payload = {key: value for key, value in proposal.items() if key != 'revision'}
            self.assertEqual(proposal['revision'], decoder_trials.run_manifest.digest(payload))
            payload['planner']['model'] = 'different'
            self.assertNotEqual(proposal['revision'], decoder_trials.run_manifest.digest(payload))
