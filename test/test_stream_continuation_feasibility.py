from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_training_feasibility as feasibility,decoder_stream_training as training
import test_stream_training as training_tests


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal initialization/continuation')
class StreamContinuationFeasibilityTests(unittest.TestCase):
    def test_low_resources_preserve_checkpoint_then_retry_advances_once_and_replay_is_noop(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
            approved=feasibility.review(root,record['id'],True,review);state=feasibility.begin(root,record['id'],True,review,approved)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile=feasibility.hardware.hardware(root);profile['available_memory_bytes']=1
            with patch.object(feasibility.hardware,'hardware',return_value=profile),patch.object(training,'step') as execute:
                with self.assertRaisesRegex(ValueError,'previous checkpoint retained'):feasibility.step(root,state['id'],True,state['revision'])
                execute.assert_not_called()
            self.assertEqual(set(before),{p for p in root.rglob('*') if p.is_file()});self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))
            result=feasibility.step(root,state['id'],True,state['revision']);self.assertEqual(result['completed_steps'],5)
            with patch.object(feasibility,'review',side_effect=AssertionError('Replay must not execute another admission/training step')):
                self.assertEqual(feasibility.step(root,state['id'],True,state['revision']),result)
            self.assertEqual(training.read(root,state['id']),result)
            with self.assertRaises(ValueError):feasibility.step(root,state['id'],False,result['revision'])

    def test_legacy_trial_gets_live_gate_and_unsupported_hardware_cannot_continue(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=training_tests.StreamTrainingTests().setup_stream(root);state=training.begin(root,record['id'],True,training.review(root,record['id']))
            profile=feasibility.hardware.hardware(root);profile['metal_available']=False
            with patch.object(feasibility.hardware,'hardware',return_value=profile),patch.object(training,'step') as execute:
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.step(root,state['id'],True,state['revision'])
                execute.assert_not_called()
            self.assertEqual(training.read(root,state['id']),state)
