import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations, decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_inputs import fixture,permissions


def larger(root):
    _,dataset=fixture(root);dataset=permissions(root,dataset)
    config={**plans.DEFAULT,'layers':3,'hidden_size':32,'attention_heads':4,'head_dim':8,'feed_forward_size':64,'context_length':16,'vocab_size':4,'seed':7,'batch_size':4}
    plan=plans.save(root,True,plans.review(config));source=initializations.run(root,plan['id'],True,plan)
    corpus=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
    settings={**training.optimizer.DEFAULT,'schema_version':5,'steps':20,'batch_size':2,'sequence_length':8,'gradient_accumulation_steps':2,
              'compute_precision':'float32','loss_scale':1.,'learning_rate':.001,'warmup_steps':3,'gradient_clip_norm':1.,'weight_decay':0.}
    return source,corpus,settings,dataset


class LargerCorpusRecipeTest(unittest.TestCase):
    def test_reviewed_recipe_admission_and_unsupported_settings_do_not_write(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base,_=larger(root);self.assertEqual(source['actual_parameter_count'],25344)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(training.hardware,'hardware',return_value=profile):
                review=isolated.review(root,source,corpus,base);self.assertTrue(review['feasible'])
                self.assertEqual(review['estimates']['gradient_accumulation_buffer_bytes'],25344*4)
                for changed in ({'batch_size':1,'gradient_accumulation_steps':1},{'gradient_accumulation_steps':1},{'compute_precision':'mixed_float16','loss_scale':128.},{'learning_rate':.005},{'schema_version':6,'steps':40}):
                    config={**base,**changed};blocked=isolated.review(root,source,corpus,config)
                    self.assertFalse(blocked['feasible']);self.assertTrue(any('25344' in value for value in blocked['blockers']))
                    with self.assertRaises(ValueError):isolated.run(root,True,source,corpus,config,blocked,uuid.uuid4().hex)
                with self.assertRaises(ValueError):isolated.run(root,False,source,corpus,base,review,uuid.uuid4().hex)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_inputs_above_absolute_cap_rejected_and_other_larger_plans_stay_blocked(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,_,base,dataset=larger(root)
            changed={**source['config'],'seed':8};plan=plans.save(root,True,plans.review(changed));other=initializations.run(root,plan['id'],True,plan)
            corpus=inputs.save(root,plan['id'],True,other,dataset,8,inputs.review(root,plan['id'],other,dataset,8))
            self.assertFalse(isolated.review(root,other,corpus,base)['feasible'])
            config={**source['config'],'layers':4,'hidden_size':64,'attention_heads':8,'feed_forward_size':128};plan=plans.save(root,True,plans.review(config));too_large=initializations.run(root,plan['id'],True,plan)
            self.assertGreater(too_large['actual_parameter_count'],131072)
            with self.assertRaisesRegex(ValueError,'131072'):inputs.review(root,plan['id'],too_large,dataset,8)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual larger-model Metal training and checkpoint continuation')
    def test_both_optimizers_restore_continue_and_generate_with_unchanged_numeric_gate(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,corpus,base,_=larger(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                record=isolated.run(root,True,source,corpus,config,isolated.review(root,source,corpus,config),uuid.uuid4().hex)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                self.assertEqual(record['completed_steps'],20);self.assertEqual(record['checkpoint_restored_steps'],10)
                self.assertTrue(record['isolated_workflow_measurements']['isolated_trial_peak_measured'])
                continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                self.assertEqual(continued['generated_token_ids'],record['generated_token_ids'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
