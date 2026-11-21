import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations
from backend import decoder_corpus_inputs as inputs, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_inputs import fixture,permissions


RECIPE={**plans.DEFAULT,'layers':3,'hidden_size':24,'attention_heads':3,'head_dim':8,'feed_forward_size':48,'vocab_size':4}


class ThreeLayerCorpusRecipeTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual compact three-layer corpus training')
    def test_seeded_recipe_trains_both_optimizers_restores_state_and_reloads_inference(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,dataset=fixture(root);dataset=permissions(root,dataset)
            review=plans.review(RECIPE);self.assertEqual(review['calculated_parameter_count'],14400);self.assertFalse(review['training_approved'])
            plan=plans.save(root,True,review);source=initializations.run(root,plan['id'],True,plan)
            self.assertEqual(source['actual_parameter_count'],14400);self.assertEqual(source['actual_weight_bytes'],57600)
            saved=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                c={**training.optimizer.DEFAULT,'schema_version':5,'steps':20,'sequence_length':8,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':'float32','loss_scale':1.,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'learning_rate':.001,'warmup_steps':3}
                record=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
                self.assertLess(record['final_losses']['train'],record['initial_losses']['train']);self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7);self.assertLessEqual(record['cpu_metal_max_error'],1e-5)
                self.assertEqual(record['completed_steps'],20);self.assertEqual(record['checkpoint_restored_steps'],10);self.assertFalse(record['pretrained_student_weights_loaded']);self.assertFalse(record['release_approved'])
                continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                self.assertEqual(continued['restored_step'],10);self.assertEqual(continued['completed_steps'],20);self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                self.assertEqual(training.read(root,record['id']),record);self.assertTrue(set(record['generated_text'].split())<={'amber','birch','cedar','dune'})
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
