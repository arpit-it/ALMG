from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_optimizer_fixture as fixture,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations
from backend.planned_decoder import PlannedDecoder
from backend import decoder_mixed_precision as mixed_precision


class DecoderOptimizerFixtureTests(unittest.TestCase):
    def source(self,root):
        plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)));return plan,initializations.run(root,plan['id'],True,plan)

    def test_versioned_settings_clipping_schedule_and_missing_moments_reject_invalid_updates(self):
        for key,value in [('optimizer','other'),('learning_rate',float('nan')),('steps',True),('warmup_steps',10),('weight_decay',.01)]:
            with self.assertRaises(ValueError):fixture.configuration({**fixture.DEFAULT,key:value})
        c=dict(fixture.DEFAULT);p={'weight':np.ones((1,),np.float32)};state={'step':0,'m':{},'v':{}}
        updated,state,entry=fixture.update(p,{'weight':np.array([100.0],np.float32)},state,c)
        self.assertAlmostEqual(entry['clip_scale'],.01);self.assertAlmostEqual(float(updated['weight'][0]),.995,places=6)
        self.assertEqual(entry['step'],1);self.assertLess(fixture.learning_rate(c,9),fixture.learning_rate(c,1))
        with self.assertRaises(ValueError):fixture.update(p,{'weight':np.array([float('nan')])},state,c)
        with self.assertRaises(ValueError):fixture.update(p,{},state,c)
        with self.assertRaises(ValueError):fixture.update(p,{'weight':np.ones((1,),np.float32)},{'step':5,'m':{},'v':{}},{**c,'optimizer':'adamw','weight_decay':.01})

    def test_adamw_checkpoint_restores_moments_and_scheduler_counter_exactly(self):
        with TemporaryDirectory() as temporary:
            model=PlannedDecoder(dict(plans.DEFAULT));c={**fixture.DEFAULT,'optimizer':'adamw','weight_decay':.01};state={'step':0,'m':{},'v':{}};parameters=model.parameters
            gradients={name:np.full_like(value,.1) for name,value in parameters.items()}
            for _ in range(5):parameters,state,_=fixture.update(parameters,gradients,state,c)
            model.parameters=parameters;path=Path(temporary)/'checkpoint';fixture.checkpoint(path,model,state,c,'review')
            restored,loaded=fixture.restore(path,c,'review');self.assertEqual(loaded['step'],5)
            for kind in ('m','v'):
                self.assertEqual(set(loaded[kind]),set(parameters));self.assertTrue(all(np.array_equal(loaded[kind][name],value) for name,value in state[kind].items()))
            a,next_state,log=fixture.update(parameters,gradients,state,c);b,resumed,resumed_log=fixture.update(restored.parameters,gradients,loaded,c)
            self.assertTrue(all(np.array_equal(a[name],value) for name,value in b.items()));self.assertEqual(log,resumed_log);self.assertEqual(next_state['step'],resumed['step'])
            with self.assertRaises(ValueError):fixture.restore(path,{**c,'learning_rate':.02},'review')
            (path/'optimizer.json').write_text('{}')
            with self.assertRaises(ValueError):fixture.restore(path,c,'review')

    def test_no_consent_or_changed_review_never_creates_optimizer_training_files(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(fixture.hardware,'hardware',return_value=profile):
                approved=fixture.review(root,plan['id'],source,dict(fixture.DEFAULT))
                with self.assertRaises(ValueError):fixture.run(root,plan['id'],False,source,dict(fixture.DEFAULT),approved)
                changed=deepcopy(approved);changed['config']['learning_rate']=.02
                with self.assertRaises(ValueError):fixture.run(root,plan['id'],True,source,dict(fixture.DEFAULT),changed)
            self.assertFalse((root/'decoder-optimizer-fixtures').exists());self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal gradients')
    def test_both_real_optimizers_reduce_loss_resume_and_reload_private_model(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for optimizer in ('sgd','adamw'):
                c={**fixture.DEFAULT,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.0};approved=fixture.review(root,plan['id'],source,c)
                report=fixture.run(root,plan['id'],True,source,c,approved)
                self.assertLess(report['final_train_loss'],report['initial_train_loss']);self.assertEqual(report['checkpoint_restored_steps'],5)
                self.assertEqual(report['completed_steps'],10);self.assertEqual(report['scheduler_completed_steps'],10)
                self.assertLessEqual(report['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(report['checkpoint_optimizer_max_error'],1e-7)
                self.assertFalse(report['pretrained_student_weights_loaded']);self.assertTrue(report['updated_weights_saved']);self.assertFalse(report['release_approved'])
                self.assertEqual(fixture.read(root,report['id']),report);self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))
            self.assertEqual(len(fixture.history(root,plan['id'],source['id'])),2)

    def test_v2_accumulation_is_token_weighted_and_legacy_config_remains_exact(self):
        self.assertEqual(fixture.configuration(dict(fixture.DEFAULT)),fixture.DEFAULT)
        c={**fixture.DEFAULT,'schema_version':2,'gradient_accumulation_steps':2}
        self.assertEqual(fixture.configuration(c)['gradient_accumulation_steps'],2)
        for value in (0,3,True):
            with self.assertRaises(ValueError):fixture.configuration({**c,'gradient_accumulation_steps':value})
        with self.assertRaises(ValueError):fixture.configuration({**fixture.DEFAULT,'gradient_accumulation_steps':2})
        result=fixture.accumulate([({'weight':np.array([1.,3.],np.float32)},3),({'weight':np.array([9.,1.],np.float32)},1)])
        np.testing.assert_array_equal(result['weight'],np.array([3.,2.5],np.float32))
        for pieces in ([],[({'w':np.ones(2)},0)],[({'w':np.ones(2)},1),({'other':np.ones(2)},1)],[({'w':np.ones(2)},1),({'w':np.ones(3)},1)],[({'w':np.array([float('nan')])},1)],[({'w':np.array([1e38],np.float32)},10)]):
            with self.assertRaises(ValueError):fixture.accumulate(pieces)

    def test_accumulation_resource_review_rejects_an_incompatible_effective_batch(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review({**plans.DEFAULT,'batch_size':1}));source=initializations.run(root,plan['id'],True,plan)
            settings={**fixture.DEFAULT,'schema_version':2,'gradient_accumulation_steps':2}
            review=fixture.review(root,plan['id'],source,settings)
            self.assertFalse(review['feasible']);self.assertIsNone(review['estimates']['microbatch_rows'])
            with self.assertRaises(ValueError):fixture.run(root,plan['id'],True,source,settings,review)
            self.assertFalse((root/'decoder-optimizer-fixtures').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real accumulated Metal gradients')
    def test_two_microbatches_match_full_gradient_and_advance_one_optimizer_step(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root)
            for optimizer in ('sgd','adamw'):
                c={**fixture.DEFAULT,'schema_version':2,'gradient_accumulation_steps':2,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.0}
                approved=fixture.review(root,plan['id'],source,c);self.assertEqual(approved['estimates']['microbatch_rows'],1)
                self.assertEqual(approved['estimates']['gradient_accumulation_buffer_bytes'],source['actual_weight_bytes'])
                report=fixture.run(root,plan['id'],True,source,c,approved)
                self.assertEqual(report['completed_steps'],10);self.assertEqual(report['scheduler_completed_steps'],10)
                self.assertEqual(report['microbatch_backward_calls_in_recorded_trajectory'],20)
                self.assertEqual([entry['step'] for entry in report['step_log']],list(range(1,11)))
                self.assertTrue(all(entry['microbatches']==2 and entry['target_tokens']==16 for entry in report['step_log']))
                self.assertLessEqual(report['full_batch_gradient_max_error'],1e-5);self.assertLessEqual(report['checkpoint_parameter_max_error'],1e-7)
                self.assertLessEqual(report['checkpoint_optimizer_max_error'],1e-7);self.assertEqual(fixture.read(root,report['id']),report)

    def test_v3_precision_and_loss_scaling_are_explicit_and_unscale_before_clipping(self):
        c={**fixture.DEFAULT,'schema_version':3,'gradient_accumulation_steps':2,'compute_precision':'mixed_float16','loss_scale':128.0}
        self.assertEqual(fixture.configuration(c),c)
        for key,value in [('compute_precision','bfloat16'),('loss_scale',1),('loss_scale',float('nan')),('loss_scale',True)]:
            with self.assertRaises(ValueError):fixture.configuration({**c,key:value})
        result=mixed_precision.unscale({'weight':np.array([128.,-256.],np.float32)},128.0)
        np.testing.assert_array_equal(result['weight'],np.array([1.,-2.],np.float32))
        with self.assertRaises(ValueError):mixed_precision.unscale({'weight':np.array([float('inf')],np.float32)},128.)
        with self.assertRaises(ValueError):mixed_precision.unscale({'weight':np.array([1.],np.float16)},128.)
        with self.assertRaises(ValueError):fixture.configuration({**c,'compute_precision':'float32'})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires mixed FP16 Metal computation')
    def test_mixed_precision_keeps_master_state_fp32_and_reloads_both_optimizers(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root)
            for optimizer in ('sgd','adamw'):
                c={**fixture.DEFAULT,'schema_version':3,'gradient_accumulation_steps':2,'compute_precision':'mixed_float16','loss_scale':128.,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.}
                approved=fixture.review(root,plan['id'],source,c);report=fixture.run(root,plan['id'],True,source,c,approved)
                self.assertEqual(report['compute_precision'],'mixed_float16');self.assertEqual(report['loss_scale'],128)
                self.assertEqual(report['master_gradient_dtype'],'float32');self.assertEqual(report['master_parameter_dtype'],'float32')
                self.assertLess(report['final_train_loss'],report['initial_train_loss']);self.assertLessEqual(report['initial_precision_loss_difference'],.05)
                self.assertLessEqual(report['causal_prefix_max_error'],1e-5);self.assertLessEqual(report['full_batch_gradient_max_error'],report['full_batch_gradient_tolerance'])
                folder=fixture._folder(root,report['id']);model,state=fixture.restore(folder/'step-5',c,report['review']['revision'])
                self.assertTrue(all(value.dtype==np.float32 for value in model.parameters.values()))
                self.assertTrue(all(value.dtype==np.float32 for kind in ('m','v') for value in state[kind].values()))
                self.assertEqual(state['step'],5);self.assertEqual(fixture.read(root,report['id']),report)
                with self.assertRaises(ValueError):fixture.restore(folder/'step-5',{**c,'loss_scale':64},report['review']['revision'])

    def test_v4_dimensions_reject_invalid_bounds_and_incompatible_plans_before_writes(self):
        settings={**fixture.DEFAULT,'schema_version':4,'gradient_accumulation_steps':1,'compute_precision':'float32','loss_scale':1.,'batch_size':1,'sequence_length':4}
        self.assertEqual(fixture.configuration(settings),settings)
        for key,value in [('batch_size',True),('batch_size',3),('sequence_length',True),('sequence_length',5)]:
            with self.assertRaises(ValueError):fixture.configuration({**settings,key:value})
        with self.assertRaises(ValueError):fixture.configuration({**settings,'schema_version':3})
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan=plans.save(root,True,plans.review({**plans.DEFAULT,'batch_size':1,'context_length':4}));source=initializations.run(root,plan['id'],True,plan)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for changed in ({'batch_size':2},{'sequence_length':8},{'gradient_accumulation_steps':2}):
                c={**settings,**changed};review=fixture.review(root,plan['id'],source,c)
                self.assertFalse(review['feasible'])
                with self.assertRaises(ValueError):fixture.run(root,plan['id'],True,source,c,review)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires configurable Metal training dimensions')
    def test_v4_executes_selected_dimensions_and_binds_checkpoint_to_them(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root)
            for precision in ('float32','mixed_float16'):
                c={**fixture.DEFAULT,'schema_version':4,'gradient_accumulation_steps':1,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.,'batch_size':1,'sequence_length':4}
                approved=fixture.review(root,plan['id'],source,c)
                self.assertEqual(approved['estimates']['effective_batch_rows'],1);self.assertEqual(approved['estimates']['sequence_length'],4);self.assertEqual(approved['estimates']['target_tokens_per_update'],4)
                report=fixture.run(root,plan['id'],True,source,c,approved)
                self.assertEqual(report['effective_batch_rows'],1);self.assertEqual(report['sequence_length'],4);self.assertEqual(report['target_tokens_per_update'],4)
                self.assertTrue(all(entry['target_tokens']==4 and entry['microbatches']==1 for entry in report['step_log']))
                self.assertLess(report['final_train_loss'],report['initial_train_loss']);self.assertEqual(report['checkpoint_parameter_max_error'],0.)
                self.assertEqual(fixture.read(root,report['id']),report)
                with self.assertRaises(ValueError):fixture.restore(fixture._folder(root,report['id'])/'step-5',{**c,'sequence_length':8},report['review']['revision'])
                with self.assertRaises(ValueError):fixture.run(root,plan['id'],True,source,{**c,'sequence_length':8},approved)

    def test_v5_budget_is_bounded_and_legacy_versions_keep_ten_update_contract(self):
        settings={**fixture.DEFAULT,'schema_version':5,'gradient_accumulation_steps':2,'compute_precision':'float32','loss_scale':1.,'batch_size':2,'sequence_length':8,'steps':20}
        self.assertEqual(fixture.configuration(settings),settings)
        for value in (True,0,11,100):
            with self.assertRaises(ValueError):fixture.configuration({**settings,'steps':value})
        for version in (1,2,3,4):
            legacy={**fixture.DEFAULT,'schema_version':version,'steps':20}
            if version>=2:legacy['gradient_accumulation_steps']=1
            if version>=3:legacy.update(compute_precision='float32',loss_scale=1.)
            if version>=4:legacy.update(batch_size=2,sequence_length=8)
            with self.assertRaises(ValueError):fixture.configuration(legacy)
        self.assertEqual(fixture.learning_rate(settings,0),.005);self.assertEqual(fixture.learning_rate(settings,1),.01)
        self.assertAlmostEqual(fixture.learning_rate(settings,19),.001)
        with self.assertRaises(ValueError):fixture.learning_rate(settings,20)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires budgeted Metal optimizer execution')
    def test_twenty_updates_restore_step_ten_and_keep_complete_scheduler_trajectory(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);plan,source=self.source(root)
            for optimizer,precision in [('sgd','float32'),('adamw','mixed_float16')]:
                c={**fixture.DEFAULT,'schema_version':5,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.,'batch_size':2,'sequence_length':8,'steps':20,'optimizer':optimizer,'weight_decay':.01 if optimizer=='adamw' else 0.}
                approved=fixture.review(root,plan['id'],source,c)
                self.assertEqual(approved['estimates']['optimizer_updates'],20);self.assertEqual(approved['estimates']['checkpoint_step'],10);self.assertEqual(approved['estimates']['recorded_microbatch_backward_calls'],40)
                report=fixture.run(root,plan['id'],True,source,c,approved)
                self.assertEqual(report['completed_steps'],20);self.assertEqual(report['scheduler_completed_steps'],20);self.assertEqual(report['checkpoint_restored_steps'],10)
                observed=report['workflow_measurements'];self.assertTrue(observed['measured']);self.assertFalse(observed['isolated_trial_peak_measured'])
                self.assertGreater(observed['elapsed_seconds'],0.);self.assertGreater(observed['process_peak_rss_bytes'],0)
                self.assertGreaterEqual(observed['sampled_active_metal_max_bytes'],observed['baseline_active_metal_bytes'])
                self.assertEqual(len(observed['phase_samples']),41)
                self.assertEqual([entry['phase'] for entry in observed['phase_samples'][:20]],[f'reference_update_{step}' for step in range(1,21)])
                self.assertEqual(observed['phase_samples'][30]['phase'],'resumed_update_11')
                self.assertEqual(report['microbatch_backward_calls_in_recorded_trajectory'],40);self.assertEqual([entry['step'] for entry in report['step_log']],list(range(1,21)))
                self.assertAlmostEqual(report['step_log'][-1]['learning_rate'],.001);self.assertLess(report['final_train_loss'],report['initial_train_loss'])
                self.assertEqual(report['checkpoint_parameter_max_error'],0.);self.assertEqual(report['checkpoint_optimizer_max_error'],0.)
                self.assertEqual(fixture.read(root,report['id']),report)
                checkpoint=fixture._folder(root,report['id'])/'step-10';model,state=fixture.restore(checkpoint,c,report['review']['revision']);self.assertEqual(state['step'],10)
                with self.assertRaises(ValueError):fixture.restore(checkpoint,{**c,'steps':10},report['review']['revision'])
                with self.assertRaises(ValueError):fixture.run(root,plan['id'],True,source,{**c,'steps':10},approved)
