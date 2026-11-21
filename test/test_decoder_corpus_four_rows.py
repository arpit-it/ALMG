import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated, decoder_corpus_inputs as inputs, decoder_datasets as datasets
from test_decoder_corpus_optimizer import corpus


def four_rows(root):
    source,saved,c=corpus(root)
    return source,saved,{**c,'schema_version':9,'batch_size':4}


class FourRowTest(unittest.TestCase):
    def test_strict_version_scope_and_synthetic_guard(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=four_rows(root)
            for accumulation in (1,2,4):
                self.assertEqual(training.configuration({**c,'gradient_accumulation_steps':accumulation},8)['batch_size'],4)
            for changes in ({'schema_version':5},{'batch_size':2},{'sequence_length':16},{'steps':40},{'compute_precision':'mixed_float16','loss_scale':128.},{'gradient_accumulation_steps':8}):
                with self.assertRaises(ValueError):training.configuration({**c,**changes},8)
            with patch.object(training.hardware,'_source') as load:
                with self.assertRaisesRegex(ValueError,'reviewed corpus workflow'):training.optimizer.review(root,source['plan_id'],source,c)
                load.assert_not_called()

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual gradient batch shapes')
    def test_selected_microbatch_count_controls_actual_gradient_batch_shapes(self):
        import mlx.core as mx
        from types import SimpleNamespace
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=four_rows(root)
            _,current,_,windows,_=training._source(root,source,saved)
            path=training.hardware.initializations._folder(root,source['plan_id'])/source['id']/'model.json'
            model=training.PlannedDecoder.load(path);original=training.backward.metal_functions
            for accumulation in (1,2,4):
                sizes=[]
                def functions(config,runtime):
                    forward,loss,gradient=original(config,runtime)
                    def traced(parameters,rows,*args):
                        sizes.append(rows.shape[0]);return gradient(parameters,rows,*args)
                    return forward,loss,traced
                c={**base,'gradient_accumulation_steps':accumulation}
                with patch.object(training.backward,'metal_functions',side_effect=functions):
                    _,state,logs,error=training.train_updates(model.parameters,{'step':0,'m':{},'v':{}},1,windows['train'],c,current['config'],mx,SimpleNamespace(sample=lambda phase:None))
                self.assertEqual(sizes,[4] if accumulation==1 else [4]+[4//accumulation]*accumulation)
                self.assertEqual(state['step'],1);self.assertEqual(len(logs),1);self.assertLessEqual(error,1e-5)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires four-token Metal training')
    def test_four_token_ten_update_recipe_and_planning_batch_admission(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=four_rows(root)
            dataset=datasets.read(root,saved['review']['dataset_id'])
            reviewed=inputs.review(root,source['plan_id'],source,dataset,4)
            saved=inputs.save(root,source['plan_id'],True,source,dataset,4,reviewed)
            c={**c,'sequence_length':4,'steps':10,'gradient_accumulation_steps':4}
            approved=isolated.review(root,source,saved,c)
            record=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
            self.assertEqual(record['completed_steps'],10);self.assertEqual(record['checkpoint_restored_steps'],5)
            self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7)
            original=training._source
            def smaller_plan(*args,**kwargs):
                result=original(*args,**kwargs)
                result[1]['config']['batch_size']=2
                return result
            with patch.object(training,'_source',side_effect=smaller_plan):
                blocked=training.review(root,source,saved,c)
            self.assertFalse(blocked['feasible'])
            self.assertTrue(any('planning batch' in reason for reason in blocked['blockers']))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual four-row Metal gradients')
    def test_weighted_microbatches_restore_and_continue_for_both_optimizers(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=four_rows(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for kind in ('sgd','adamw'):
                for accumulation in (1,2,4):
                    c={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'gradient_accumulation_steps':accumulation}
                    approved=isolated.review(root,source,saved,c)
                    self.assertEqual(approved['estimates']['microbatch_rows'],4//accumulation)
                    record=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                    self.assertEqual(record['completed_steps'],20);self.assertEqual(record['checkpoint_restored_steps'],10)
                    self.assertLessEqual(record['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(record['checkpoint_optimizer_max_error'],1e-7)
                    self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                    for entry in record['step_log']:
                        self.assertEqual(len(entry['window_indices']),4)
                        self.assertEqual(entry['microbatches'],accumulation)
                    continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                    self.assertLessEqual(continued['reference_parameter_max_error'],1e-7)
                    self.assertEqual(training.read(root,record['id']),record)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
