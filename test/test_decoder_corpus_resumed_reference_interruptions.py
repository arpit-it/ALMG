"""Real interruption of separately approved reference recovery workers."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_optimizer as training, decoder_corpus_interruptions as interruptions, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus
from test_decoder_corpus_interruptions import HOOK


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual resumed worker termination and Metal checkpoint recovery')
class ResumedReferenceWorkerInterruptionTest(unittest.TestCase):
    def test_interrupted_recovery_keeps_ancestry_and_can_be_approved_again(self):
        for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
            for counter in (0,30):
                with self.subTest(optimizer=kind,counter=counter),TemporaryDirectory() as temporary:
                    root=Path(temporary);source,saved,settings=corpus(root)
                    c={**settings,'schema_version':6,'steps':40,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                    approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;original=training.optimizer.update;calls=0
                    def stop(*args,**kwargs):
                        nonlocal calls
                        result=original(*args,**kwargs);calls+=1
                        if calls==counter:training.run_cancellation.request(root,approved,token,True)
                        return result
                    if counter==0:training.run_cancellation.request(root,approved,token,True)
                    with patch.object(training.optimizer,'update',side_effect=stop):parent=training.run(root,True,source,saved,c,approved,request_id=token)
                    self.assertEqual(parent['completed_steps'],counter)
                    hooks=root/'hooks';hooks.mkdir();(hooks/'sitecustomize.py').write_text(HOOK)
                    approved=isolated.review_reference_resume(root,parent['id']);token=uuid.uuid4().hex;point=20 if counter==0 else 30
                    env={**os.environ,'PYTHONPATH':str(hooks)+os.pathsep+str(Path(__file__).resolve().parent.parent),'ALMG_INTERRUPTION_TEST_ROOT':str(root),'ALMG_INTERRUPTION_TEST_PHASE':'1','ALMG_INTERRUPTION_TEST_STEP':str(point+1)}
                    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                    try:
                        process.stdin.write(json.dumps({'root':str(root),'identifier':parent['id'],'approved':approved,'request_id':token,'nonce':uuid.uuid4().hex,'action':'reference_resume'}));process.stdin.close();process.stdin=None
                        deadline=time.monotonic()+15
                        while not (root/'progress.json').exists():
                            if process.poll() is not None:self.fail(process.communicate()[1])
                            self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                        records=[training.read(root,p.parent.name) for p in (root/interruptions.DIRECTORY).glob('*/record.json')]
                        self.assertEqual(len(records),3 if counter==0 else 1)
                        record=max(records,key=interruptions.progress)
                        self.assertEqual((record['schema_version'],record['checkpoint_origin'],record['completed_steps']),(12,'resumed_worker_reference_progress',point))
                        self.assertEqual(record['reference_resume_depth'],1);self.assertEqual(record['reference_steps_carried'],counter);self.assertEqual(record['reference_updates_executed'],point-counter)
                        self.assertEqual(record['review']['reference_resume_from']['record_id'],parent['id']);self.assertEqual(record['recorded_training_updates'],0)
                        self.assertEqual(record['owner_process_id'],process.pid);self.assertEqual(record['owner_parent_process_id'],os.getpid())
                        with self.assertRaisesRegex(ValueError,'still active'):isolated.review_reference_resume(root,record['id'])
                        process.kill();process.communicate(timeout=10)
                    finally:
                        if process.poll() is None:process.kill();process.communicate(timeout=10)
                    self.assertFalse((root/'decoder-corpus-run-cancellation-requests'/f'{token}.json').exists())
                    self.assertIn(record,interruptions.history(root,source,saved))
                    self.assertFalse((root/'decoder-corpus-optimizer-runs'/record['original_run_id']/'record.json').exists())
                    retained={p:p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name!='progress.json'}
                    with patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):isolated.run_reference_resume(root,record['id'],False,None)
                        spawn.assert_not_called()
                    result=isolated.run_reference_resume(root,record['id'],True,isolated.review_reference_resume(root,record['id']),uuid.uuid4().hex)
                    self.assertEqual(result['reference_resume_depth'],2);self.assertEqual(result['reference_steps_carried'],point);self.assertEqual(result['reference_updates_executed'],40-point)
                    self.assertEqual(result['checkpoint_restored_steps'],20);self.assertEqual(result['completed_steps'],40)
                    self.assertEqual(result['checkpoint_parameter_max_error'],0);self.assertEqual(result['checkpoint_optimizer_max_error'],0)
                    self.assertEqual(training.read(root,result['id']),result)
                    self.assertTrue(all(p.read_bytes()==data for p,data in {**before,**retained}.items()))
