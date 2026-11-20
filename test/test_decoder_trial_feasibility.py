from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_trial_feasibility as feasibility,decoder_trials as trials
from backend.decoder_recipe import Decoder


def hardware():
    return {'system':'Darwin','machine':'arm64','metal_available':True,'mlx_version':'fixture','metal_device':{'device_name':'Fixture GPU','max_recommended_working_set_size':8*1024**3},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}


class DecoderTrialFeasibilityTests(unittest.TestCase):
    def test_review_allocates_no_weights_and_binds_exact_unchanged_generated_specification(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);model=Decoder({'vocab_size':4,'seed':7})
            with patch.object(feasibility.architecture,'hardware',return_value=hardware()),patch.object(Decoder,'__init__',side_effect=AssertionError('Review must not construct weights')):
                report=feasibility.review(root)
            self.assertTrue(report['feasible']);self.assertEqual(report['estimates']['parameter_bytes'],sum(value.nbytes for value in model.parameters.values()))
            self.assertEqual(report['specification_sha256'],feasibility.digest(trials.specification()));self.assertFalse(report['estimates']['measured']);self.assertEqual(list(root.iterdir()),[])

    def test_consent_stale_review_unsupported_hardware_and_low_resources_never_submit(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(feasibility.architecture,'hardware',return_value=hardware()):approved=feasibility.review(root)
            with patch.object(trials,'start') as start:
                with self.assertRaises(ValueError):feasibility.start(root,False,lambda *args:None,approved)
                stale=deepcopy(approved);stale['estimates']['parameter_bytes']=0
                with patch.object(feasibility.architecture,'hardware',return_value=hardware()):
                    with self.assertRaisesRegex(ValueError,'review changed'):feasibility.start(root,True,lambda *args:None,stale)
                for key,value in [('metal_available',False),('available_memory_bytes',1),('free_disk_bytes',1),('machine','x86_64')]:
                    profile=hardware();profile[key]=value
                    with patch.object(feasibility.architecture,'hardware',return_value=profile):
                        with self.assertRaisesRegex(ValueError,'blocked'):feasibility.start(root,True,lambda *args:None,approved)
                start.assert_not_called()
            self.assertFalse((root/'decoder-trials').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real generated-trial Metal execution')
    def test_profile_is_saved_before_worker_and_survives_actual_training_and_reload(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);approved=feasibility.review(root);queued=[]
            record=feasibility.start(root,True,lambda function,*args:queued.append((function,args)),approved)
            saved=trials.read(root,record['id']);profile=saved['generated_trial_hardware']
            self.assertTrue(profile['reviewed_before_approval']);self.assertEqual(profile['approval'],approved)
            self.assertEqual(saved['approval']['revision'],trials.approval_revision(saved))
            function,args=queued.pop();function(*args)
            restored=trials.read(root,record['id']);self.assertEqual(restored['status'],'complete',restored.get('error'))
            self.assertEqual(restored['generated_trial_hardware'],profile)
            self.assertLess(restored['result']['final_loss'],restored['result']['initial_loss'])
            self.assertLessEqual(restored['result']['checkpoint']['uninterrupted_max_error'],1e-6)
            self.assertFalse(restored['result']['pretrained_weights_loaded'])
