import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_architecture_plans as plans,decoder_architecture_initializations as initializations,decoder_architecture_backward as backward
from backend.run_manifest import digest


class ArchitectureBackwardTests(unittest.TestCase):
    def fixture(self,root,config):
        plan=plans.save(root,True,plans.review(config))
        return initializations.run(root,plan['id'],True,plan)

    def test_consent_and_stale_review_reject_before_metal_functions(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root,dict(plans.DEFAULT))
            with patch.object(backward,'metal_functions') as functions:
                with self.assertRaises(ValueError):backward.run(root,record['plan_id'],False,record)
                with self.assertRaises(ValueError):backward.run(root,record['plan_id'],True,{**record,'steps':'changed'})
                functions.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal autodiff')
    def test_all_native_layouts_backward_finite_differences_and_immutable_weights(self):
        for layers,width,heads,ff in ((1,8,1,16),(2,16,2,32),(4,64,4,256)):
            with self.subTest(layers=layers),TemporaryDirectory() as temporary:
                root=Path(temporary);record=self.fixture(root,{**plans.DEFAULT,'layers':layers,'hidden_size':width,'attention_heads':heads,'head_dim':width//heads,'feed_forward_size':ff})
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                result=backward.run(root,record['plan_id'],True,record)
                observed=result['diagnostic_measurements']
                self.assertGreater(observed['elapsed_seconds'],0)
                self.assertEqual(len(observed['samples']),7)
                self.assertGreater(observed['sampled_active_metal_max_bytes'],0)
                self.assertGreaterEqual(observed['conservative_observed_gpu_budget_bytes'],observed['estimated_gpu_working_bytes'])
                self.assertFalse(observed['isolated_trial_peak_measured'])
                self.assertLess(result['final_loss'],result['initial_loss']);self.assertEqual(len(result['changed_parameter_tensors']),result['parameter_tensors'])
                self.assertTrue(result['padding_check_applicable']);self.assertGreater(result['padded_targets_changed'],0)
                self.assertLessEqual(result['padding_gradient_error'],1e-6);self.assertLessEqual(result['padding_loss_error'],1e-6)
                self.assertTrue(all(item['absolute_error']<=item['tolerance'] for item in result['finite_difference_probes']))
                self.assertFalse(result['updated_weights_saved']);self.assertFalse(result['training_approved']);self.assertFalse(result['release_approved'])
                importlib.reload(backward);self.assertEqual(backward.list_reports(root,record['plan_id'],True),[result])
                previous={k:v for k,v in result.items() if k!='diagnostic_measurements'}
                previous.update(format='almg-planned-decoder-backward-check-v2',schema_version=2,id='1'*32)
                previous['revision']=digest({k:v for k,v in previous.items() if k!='revision'})
                (backward._folder(root,record['plan_id'])/('1'*32+'.json')).write_text(json.dumps(previous))
                self.assertIn(previous,backward.list_reports(root,record['plan_id'],True))
                legacy={k:v for k,v in result.items() if k not in ('hardware_feasibility','approved_feasibility_revision','diagnostic_measurements')}
                legacy.update(format='almg-planned-decoder-backward-check-v1',schema_version=1,id='0'*32)
                legacy['revision']=digest({k:v for k,v in legacy.items() if k!='revision'})
                (backward._folder(root,record['plan_id'])/('0'*32+'.json')).write_text(json.dumps(legacy))
                self.assertIn(legacy,backward.list_reports(root,record['plan_id'],True))
                self.assertIn(result,backward.list_reports(root,record['plan_id'],True))
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal autodiff')
    def test_minimum_context_and_batch_have_nonvacuous_attention_gradients(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root,{**plans.DEFAULT,'context_length':2,'batch_size':1,'vocab_size':4})
            result=backward.run(root,record['plan_id'],True,record)
            self.assertFalse(result['padding_check_applicable']);self.assertEqual(result['real_target_tokens'],2)
            self.assertGreater(result['gradient_norms']['layers.0.query'],0)
            self.assertLess(result['final_loss'],result['initial_loss'])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal autodiff')
    def test_wrong_gradient_and_failed_publication_never_change_initialized_model(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root,dict(plans.DEFAULT));before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            original=backward.metal_functions
            def wrong(config,mx):
                logits,loss,grad=original(config,mx)
                def gradient(*args):
                    value=grad(*args);value['head']=value['head']+.1;return value
                return logits,loss,gradient
            with patch.object(backward,'metal_functions',side_effect=wrong):
                with self.assertRaisesRegex(ValueError,'finite-difference'):backward.run(root,record['plan_id'],True,record)
            with patch.object(Path,'replace',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):backward.run(root,record['plan_id'],True,record)
            self.assertEqual(backward.list_reports(root,record['plan_id'],True),[])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
