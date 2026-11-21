import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations, decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_larger_recipe import larger


def seven_layers(root):
    _,_,settings,dataset=larger(root)
    config={**plans.DEFAULT,'layers':7,'hidden_size':64,'attention_heads':8,'head_dim':8,'feed_forward_size':128,'context_length':16,'vocab_size':4,'seed':7,'batch_size':4}
    plan=plans.save(root,True,plans.review(config));source=initializations.run(root,plan['id'],True,plan)
    corpus=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
    return source,corpus,settings


class SevenLayerCorpusRecipeTest(unittest.TestCase):
    def test_fixed_shape_settings_and_resource_gate_preserved(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=seven_layers(root)
            self.assertEqual(source['actual_parameter_count'],230912)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                for kind in ('sgd','adamw'):
                    c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                    self.assertTrue(isolated.review(root,source,corpus,c)['feasible'])
                for changes in ({'learning_rate':.005},{'gradient_accumulation_steps':1},{'compute_precision':'mixed_float16','loss_scale':128.},{'schema_version':6,'steps':40}):
                    c={**base,**changes};review=isolated.review(root,source,corpus,c)
                    self.assertFalse(review['feasible'])
                    with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,c,review,uuid.uuid4().hex)
            profile.update(available_memory_bytes=1,free_disk_bytes=1)
            with patch.object(training.hardware,'hardware',return_value=profile):
                review=isolated.review(root,source,corpus,base);self.assertFalse(review['feasible'])
                with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,base,review,uuid.uuid4().hex)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual seven-layer Metal training and fresh continuation')
    def test_real_optimizers_compact_restore_and_generation(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base=seven_layers(root);base={**base,'steps':10}
            for kind in ('sgd','adamw'):
                c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                record=isolated.run(root,True,source,corpus,c,isolated.review(root,source,corpus,c),uuid.uuid4().hex)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7)
                self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                self.assertEqual(continued['generated_token_ids'],record['generated_token_ids'])
