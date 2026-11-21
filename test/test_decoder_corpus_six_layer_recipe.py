import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations, decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_larger_recipe import larger


def six_layers(root):
    _,_,settings,dataset=larger(root)
    config={**plans.DEFAULT,'layers':6,'hidden_size':48,'attention_heads':6,'head_dim':8,'feed_forward_size':96,'context_length':16,'vocab_size':4,'seed':7,'batch_size':4}
    plan=plans.save(root,True,plans.review(config));source=initializations.run(root,plan['id'],True,plan)
    corpus=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
    return source,corpus,settings


class SixLayerCorpusRecipeTest(unittest.TestCase):
    def test_specific_profiled_shape_and_settings_resource_review(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=six_layers(root);self.assertEqual(source['actual_parameter_count'],111744)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(training.hardware,'hardware',return_value=profile):
                for kind in ('sgd','adamw'):
                    config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                    reviewed=isolated.review(root,source,corpus,config);self.assertTrue(reviewed['feasible'])
                    self.assertEqual(reviewed['estimates']['gradient_accumulation_buffer_bytes'],111744*4)
                for changed in ({'batch_size':1,'gradient_accumulation_steps':1},{'compute_precision':'mixed_float16','loss_scale':128.},{'learning_rate':.005},{'schema_version':6,'steps':40}):
                    config={**base,**changed};reviewed=isolated.review(root,source,corpus,config)
                    self.assertFalse(reviewed['feasible']);self.assertTrue(any('111744' in value for value in reviewed['blockers']))
                    with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,config,reviewed,uuid.uuid4().hex)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_available_memory_denial_keeps_larger_recipe_blocked(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=six_layers(root)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':1,'free_disk_bytes':1,'errors':[]}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(training.hardware,'hardware',return_value=profile):
                review=isolated.review(root,source,corpus,base);self.assertFalse(review['feasible'])
                with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,base,review,uuid.uuid4().hex)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual six-layer Metal training and fresh continuations')
    def test_both_optimizers_restore_continue_and_reload_generated_tokens(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=six_layers(root);base={**base,'steps':10}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                record=isolated.run(root,True,source,corpus,config,isolated.review(root,source,corpus,config),uuid.uuid4().hex)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                self.assertEqual(record['checkpoint_restored_steps'],5)
                self.assertGreater(record['isolated_workflow_measurements']['isolated_metal_peak_bytes'],0)
                continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                self.assertEqual(continued['generated_token_ids'],record['generated_token_ids'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
