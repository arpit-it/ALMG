import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class FortyUpdateTest(unittest.TestCase):
    def test_version_six_requires_forty_updates_and_corpus_admission(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);c={**settings,'schema_version':6,'steps':40}
            self.assertEqual(training.configuration(c,8),c)
            for changes in ({'schema_version':5},{'steps':20},{'steps':10},{'steps':80},{'steps':40.0},{'steps':True}):
                with self.assertRaises(ValueError):training.configuration({**c,**changes},8)
            with patch.object(training.hardware,'_source') as load:
                with self.assertRaisesRegex(ValueError,'reviewed corpus workflow'):training.optimizer.review(root,source['plan_id'],source,c)
                load.assert_not_called()
            with self.assertRaises(ValueError):training.run(root,False,source,saved,c,None)
            self.assertFalse((root/'decoder-corpus-optimizer-runs').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires version-six Metal corpus execution')
    def test_both_optimizers_complete_forty_updates_and_resume_both_phases_with_twenty_step_midpoints(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);original=training.optimizer.update
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'schema_version':6,'steps':40,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                approved=isolated.review(root,source,saved,c);self.assertEqual(approved['estimates']['optimizer_updates'],40);self.assertEqual(approved['estimates']['checkpoint_step'],20)
                completed=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                self.assertEqual(completed['completed_steps'],40);self.assertEqual(completed['checkpoint_restored_steps'],20);self.assertEqual(len(completed['step_log']),40)
                self.assertAlmostEqual(completed['step_log'][-1]['learning_rate'],.001)
                self.assertLess(completed['final_losses']['train'],completed['initial_losses']['train']);self.assertLessEqual(completed['checkpoint_optimizer_max_error'],1e-7)
                self.assertEqual(training.read(root,completed['id']),completed)
                self.assertEqual(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate']['sample_count'],1)
                self.assertIsNone(isolated.review(root,source,saved,{**c,'schema_version':5,'steps':20})['estimates']['corpus_work_estimate'])
                continuation=isolated.run_continuation(root,completed['id'],True,isolated.review_continuation(root,completed['id']),uuid.uuid4().hex)
                self.assertEqual(continuation['restored_step'],20);self.assertEqual(continuation['completed_steps'],40);self.assertLessEqual(continuation['reference_parameter_max_error'],1e-7)
                for target,phase in ((61,'training'),(1,'reference')):
                    approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;calls=0
                    def stop(*args):
                        nonlocal calls
                        result=original(*args);calls+=1
                        if calls==target:training.run_cancellation.request(root,approved,token,True)
                        return result
                    with patch.object(training.optimizer,'update',side_effect=stop):parent=training.run(root,True,source,saved,c,approved,request_id=token)
                    reviewer=isolated.review_training_resume if phase=='training' else isolated.review_reference_resume
                    runner=isolated.run_training_resume if phase=='training' else isolated.run_reference_resume
                    resumed=runner(root,parent['id'],True,reviewer(root,parent['id']),uuid.uuid4().hex)
                    self.assertEqual(resumed['completed_steps'],40);self.assertEqual(resumed['checkpoint_restored_steps'],20)
                    self.assertLessEqual(resumed['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(resumed['checkpoint_optimizer_max_error'],1e-7)
                    self.assertEqual(resumed['reference_updates_executed'],0 if phase=='training' else 39)
                    if phase=='training':self.assertEqual(resumed['training_steps_carried'],21);self.assertEqual(resumed['training_updates_executed'],19)
                    self.assertEqual(training.read(root,resumed['id']),resumed)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
