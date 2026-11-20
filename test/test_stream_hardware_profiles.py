import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_training_feasibility as feasibility,decoder_stream_training as training
import test_stream_training as training_tests


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual Metal training')
class StreamHardwareProfileTests(unittest.TestCase):
    def fixture(self,root):
        record=training_tests.StreamTrainingTests().setup_stream(root);review=training.review(root,record['id'])
        approved=feasibility.review(root,record['id'],True,review)
        return record,review,approved

    def test_profile_retains_snapshots_after_restart_and_continuation_and_rejects_tampering(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,review,approved=self.fixture(root)
            state=feasibility.begin(root,record['id'],True,review,approved)
            profile=feasibility.read_profile(root,state['id'],True);self.assertTrue(profile['available'])
            self.assertEqual(profile['record']['approved_feasibility'],approved)
            self.assertTrue(profile['record']['execution_feasibility']['feasible'])
            path=training._folder(root,state['id'])/'hardware-feasibility.json';before=path.read_bytes()
            with self.assertRaises(ValueError):feasibility.read_profile(root,state['id'],False)
            state=training.step(root,state['id'],True,state['revision']);importlib.reload(feasibility)
            self.assertEqual(feasibility.read_profile(root,state['id'],True),profile);self.assertEqual(path.read_bytes(),before)
            changed=json.loads(before);changed['approval_sha256']='0'*64;path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):feasibility.read_profile(root,state['id'],True)

    def test_legacy_absence_and_publication_failure_preserve_initialized_checkpoint(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,review,approved=self.fixture(root)
            legacy=training.begin(root,record['id'],True,review)
            self.assertFalse(feasibility.read_profile(root,legacy['id'],True)['available'])
            with patch.object(feasibility,'_save_profile',side_effect=OSError('fixture disk failure')):
                with self.assertRaisesRegex(ValueError,'checkpoint is retained'):feasibility.begin(root,record['id'],True,review,approved)
            runs=training.list_runs(root,record['id'],True);self.assertEqual(len(runs),2)
            self.assertTrue(all(state['completed_steps']==0 for state in runs))
