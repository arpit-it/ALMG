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

HOOK='''import os,sys,time,json
from pathlib import Path
root=Path(os.environ['ALMG_INTERRUPTION_TEST_ROOT']);calls=0
def profile(frame,event,arg):
 global calls
 if event=='call' and frame.f_code.co_name=='train_updates' and frame.f_globals.get('__name__')=='backend.decoder_corpus_optimizer':
  calls+=1
  if calls==3:
   original=frame.f_globals['optimizer'].update
   def paced(*args,**kwargs):
    result=original(*args,**kwargs);(root/'progress.json').write_text(json.dumps({'pid':os.getpid(),'step':result[1]['step']}));time.sleep(30);return result
   frame.f_globals['optimizer'].update=paced;sys.setprofile(None)
sys.setprofile(profile)
'''


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual worker termination and durable Metal checkpoint recovery')
class InterruptionCheckpointTest(unittest.TestCase):
    def test_killed_workers_recover_frozen_midpoint_with_separate_approval_and_no_cancel_receipt(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root);hooks=root/'hooks';hooks.mkdir();(hooks/'sitecustomize.py').write_text(HOOK)
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'schema_version':6,'steps':40,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex;progress=root/'progress.json';progress.unlink(missing_ok=True)
                env={**os.environ,'PYTHONPATH':str(hooks)+os.pathsep+str(Path(__file__).resolve().parent.parent),'ALMG_INTERRUPTION_TEST_ROOT':str(root)}
                process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                try:
                    process.stdin.write(json.dumps({'root':str(root),'initialized':source,'corpus':saved,'settings':c,'approved':approved,'request_id':token,'nonce':uuid.uuid4().hex,'action':'full'}));process.stdin.close();process.stdin=None
                    deadline=time.monotonic()+15
                    while not progress.exists():
                        if process.poll() is not None:self.fail(process.communicate()[1])
                        self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                    self.assertEqual(json.loads(progress.read_text()),{'pid':process.pid,'step':21})
                    paths=[p for p in (root/interruptions.DIRECTORY).glob('*/record.json') if json.loads(p.read_text())['owner_process_id']==process.pid];self.assertEqual(len(paths),1)
                    record=training.read(root,paths[0].parent.name);self.assertEqual(record['status'],'interruption_checkpoint');self.assertEqual(record['completed_steps'],20)
                    self.assertEqual(record['reference_completed_steps'],40);self.assertFalse(record['reference_verified']);self.assertFalse(record['release_approved'])
                    self.assertFalse(interruptions.recoverable(root,record));self.assertNotIn(record,interruptions.history(root,source,saved))
                    with self.assertRaisesRegex(ValueError,'still active'):isolated.review_training_resume(root,record['id'])
                    process.kill();process.communicate(timeout=10)
                finally:
                    if process.poll() is None:process.kill();process.communicate(timeout=10)
                self.assertTrue(interruptions.recoverable(root,record));self.assertIn(record,interruptions.history(root,source,saved))
                self.assertFalse((root/'decoder-corpus-run-cancellation-requests'/f'{token}.json').exists())
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with patch.object(isolated.subprocess,'Popen') as spawn:
                    with self.assertRaises(ValueError):isolated.run_training_resume(root,record['id'],False,None)
                    spawn.assert_not_called()
                resumed=isolated.run_training_resume(root,record['id'],True,isolated.review_training_resume(root,record['id']),uuid.uuid4().hex)
                self.assertEqual(resumed['training_steps_carried'],20);self.assertEqual(resumed['training_updates_executed'],20);self.assertEqual(resumed['reference_updates_executed'],0)
                self.assertEqual(resumed['completed_steps'],40);self.assertLessEqual(resumed['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(resumed['checkpoint_optimizer_max_error'],1e-7)
                self.assertEqual(training.read(root,resumed['id']),resumed);self.assertEqual(training.read(root,record['id']),record)
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                path=paths[0].parent/'optimizer.json';original=path.read_bytes();data=json.loads(original);data['step']+=1;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):training.read(root,record['id'])
                path.write_bytes(original)

    def test_completed_origins_are_not_offered_as_interrupted(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root)
            record=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
            checkpoints=list((root/interruptions.DIRECTORY).glob('*/record.json'));self.assertEqual(len(checkpoints),1)
            retained=training.read(root,checkpoints[0].parent.name)
            self.assertEqual(retained['original_run_id'],record['id']);self.assertEqual(interruptions.history(root,source,saved),[])
            with self.assertRaisesRegex(ValueError,'terminal result'):isolated.review_training_resume(root,retained['id'])

    def test_failed_publication_preserves_files_and_never_exposes_partial_manifest(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);review=isolated.review(root,source,saved,c)
            with patch.object(interruptions,'flush_files',side_effect=OSError('injected flush failure')):
                with self.assertRaisesRegex(OSError,'injected flush'):training.run(root,True,source,saved,c,review,'fresh_process',uuid.uuid4().hex)
            self.assertEqual(list((root/interruptions.DIRECTORY).glob('*/record.json')),[])
            self.assertTrue(list((root/interruptions.DIRECTORY).glob('*/trained-model.json')))
            self.assertEqual(interruptions.history(root,source,saved),[])


class InterruptionProbeTest(unittest.TestCase):
    def test_non_posix_discovery_never_sends_process_signals(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        with TemporaryDirectory() as temporary:
            probe=Mock()
            with patch.object(interruptions,'os',SimpleNamespace(name='nt',kill=probe)):
                self.assertFalse(interruptions.recoverable(Path(temporary),{'original_run_id':'a'*32,'owner_process_id':123}))
            probe.assert_not_called()
