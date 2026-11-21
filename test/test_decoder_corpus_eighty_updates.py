import os
import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus
from test_decoder_corpus_interruptions import HOOK
from backend import decoder_corpus_interruptions as interruptions


class EightyUpdateTest(unittest.TestCase):
    def test_version_seven_requires_eighty_updates_and_corpus_admission(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);c={**settings,'schema_version':7,'steps':80}
            self.assertEqual(training.configuration(c,8),c)
            for changes in ({'schema_version':5},{'schema_version':6},{'steps':20},{'steps':10},{'steps':40},{'steps':80.0},{'steps':True}):
                with self.assertRaises(ValueError):training.configuration({**c,**changes},8)
            with patch.object(training.hardware,'_source') as load:
                with self.assertRaisesRegex(ValueError,'reviewed corpus workflow'):training.optimizer.review(root,source['plan_id'],source,c)
                load.assert_not_called()
            with self.assertRaises(ValueError):training.run(root,False,source,saved,c,None)
            self.assertFalse((root/'decoder-corpus-optimizer-runs').exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires version-seven Metal corpus execution')
    def test_both_optimizers_complete_eighty_updates_and_resume_both_phases_with_forty_step_midpoints(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);original=training.optimizer.update
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'schema_version':7,'steps':80,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                approved=isolated.review(root,source,saved,c);self.assertEqual(approved['estimates']['optimizer_updates'],80);self.assertEqual(approved['estimates']['checkpoint_step'],40)
                completed=isolated.run(root,True,source,saved,c,approved,uuid.uuid4().hex)
                self.assertEqual(completed['completed_steps'],80);self.assertEqual(completed['checkpoint_restored_steps'],40);self.assertEqual(len(completed['step_log']),80)
                self.assertAlmostEqual(completed['step_log'][-1]['learning_rate'],.001)
                self.assertLess(completed['final_losses']['train'],completed['initial_losses']['train']);self.assertLessEqual(completed['checkpoint_optimizer_max_error'],1e-7)
                self.assertEqual(training.read(root,completed['id']),completed)
                self.assertEqual(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate']['sample_count'],1)
                self.assertIsNone(isolated.review(root,source,saved,{**c,'schema_version':5,'steps':20})['estimates']['corpus_work_estimate'])
                continuation=isolated.run_continuation(root,completed['id'],True,isolated.review_continuation(root,completed['id']),uuid.uuid4().hex)
                self.assertEqual(continuation['restored_step'],40);self.assertEqual(continuation['completed_steps'],80);self.assertLessEqual(continuation['reference_parameter_max_error'],1e-7)
                for target,phase in ((121,'training'),(1,'reference')):
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
                    self.assertEqual(resumed['completed_steps'],80);self.assertEqual(resumed['checkpoint_restored_steps'],40)
                    self.assertLessEqual(resumed['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(resumed['checkpoint_optimizer_max_error'],1e-7)
                    self.assertEqual(resumed['reference_updates_executed'],0 if phase=='training' else 79)
                    if phase=='training':self.assertEqual(resumed['training_steps_carried'],41);self.assertEqual(resumed['training_updates_executed'],39)
                    self.assertEqual(training.read(root,resumed['id']),resumed)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual eighty-update worker interruption')
    def test_eighty_update_worker_restores_reference_forty_after_termination(self):
        for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
            with self.subTest(optimizer=kind),TemporaryDirectory() as temporary:
                root=Path(temporary);source,saved,settings=corpus(root)
                c={**settings,'schema_version':7,'steps':80,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex;hooks=root/'hooks';hooks.mkdir();(hooks/'sitecustomize.py').write_text(HOOK)
                env={**os.environ,'PYTHONPATH':str(hooks)+os.pathsep+str(Path(__file__).resolve().parent.parent),'ALMG_INTERRUPTION_TEST_ROOT':str(root),'ALMG_INTERRUPTION_TEST_PHASE':'1','ALMG_INTERRUPTION_TEST_STEP':'41'}
                process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                try:
                    process.stdin.write(json.dumps({'root':str(root),'initialized':source,'corpus':saved,'settings':c,'approved':approved,'request_id':token,'nonce':uuid.uuid4().hex,'action':'full'}));process.stdin.close();process.stdin=None
                    deadline=time.monotonic()+15
                    while not (root/'progress.json').exists():
                        if process.poll() is not None:self.fail(process.communicate()[1])
                        self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                    records=[training.read(root,p.parent.name) for p in (root/interruptions.DIRECTORY).glob('*/record.json')];self.assertEqual(len(records),3)
                    record=max(records,key=interruptions.progress);self.assertEqual(record['completed_steps'],40);self.assertEqual(record['reference_completed_steps'],40);self.assertEqual(record['recorded_training_updates'],0)
                    self.assertEqual(record['owner_process_id'],process.pid)
                    with self.assertRaisesRegex(ValueError,'still active'):isolated.review_reference_resume(root,record['id'])
                    process.kill();process.communicate(timeout=10)
                finally:
                    if process.poll() is None:process.kill();process.communicate(timeout=10)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                result=isolated.run_reference_resume(root,record['id'],True,isolated.review_reference_resume(root,record['id']),uuid.uuid4().hex)
                self.assertEqual(result['reference_steps_carried'],40);self.assertEqual(result['reference_updates_executed'],40)
                self.assertEqual(result['completed_steps'],80);self.assertEqual(result['checkpoint_restored_steps'],40);self.assertEqual(result['checkpoint_parameter_max_error'],0);self.assertEqual(result['checkpoint_optimizer_max_error'],0)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
