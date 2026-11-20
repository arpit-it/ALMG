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
