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
  if calls==int(os.environ.get('ALMG_INTERRUPTION_TEST_PHASE','3')):
   original=frame.f_globals['optimizer'].update
   def paced(*args,**kwargs):
    result=original(*args,**kwargs)
    if result[1]['step']>=int(os.environ.get('ALMG_INTERRUPTION_TEST_STEP','0')):(root/'progress.json').write_text(json.dumps({'pid':os.getpid(),'step':result[1]['step']}));time.sleep(30)
    return result
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
                for phase_call,counter,reference_phase in ((1,0,True),(1,10,True),(1,20,True),(1,30,True),(2,0,False),(2,10,False),(3,20,False),(3,30,False)):
                    approved=isolated.review(root,source,saved,c);token=uuid.uuid4().hex;progress=root/'progress.json';progress.unlink(missing_ok=True)
                    env={**os.environ,'PYTHONPATH':str(hooks)+os.pathsep+str(Path(__file__).resolve().parent.parent),'ALMG_INTERRUPTION_TEST_ROOT':str(root),'ALMG_INTERRUPTION_TEST_PHASE':str(phase_call),'ALMG_INTERRUPTION_TEST_STEP':str(counter+1)}
                    process=subprocess.Popen([sys.executable,'-m','backend.decoder_corpus_worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                    try:
                        process.stdin.write(json.dumps({'root':str(root),'initialized':source,'corpus':saved,'settings':c,'approved':approved,'request_id':token,'nonce':uuid.uuid4().hex,'action':'full'}));process.stdin.close();process.stdin=None
                        deadline=time.monotonic()+15
                        while not progress.exists():
                            if process.poll() is not None:self.fail(process.communicate()[1])
                            self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                        self.assertEqual(json.loads(progress.read_text()),{'pid':process.pid,'step':counter+1})
                        paths=[p for p in (root/interruptions.DIRECTORY).glob('*/record.json') if json.loads(p.read_text())['owner_process_id']==process.pid];self.assertEqual(len(paths),counter//10+(1 if reference_phase else 5))
                        path=max(paths,key=lambda p:interruptions.progress(json.loads(p.read_text())));record=training.read(root,path.parent.name);self.assertEqual(record['status'],'interruption_checkpoint');self.assertEqual(record['completed_steps'],counter)
                        self.assertEqual(record['schema_version'],(7 if counter==0 else 8 if counter==20 else 9) if reference_phase else 6 if counter==0 else 5 if counter==20 else 10);self.assertEqual(record['reference_completed_steps'],counter if reference_phase else 40);self.assertFalse(record['reference_verified']);self.assertFalse(record['release_approved'])
                        self.assertFalse(interruptions.recoverable(root,record));self.assertNotIn(record,interruptions.history(root,source,saved))
                        reviewer=isolated.review_reference_resume if reference_phase else isolated.review_training_resume
                        runner=isolated.run_reference_resume if reference_phase else isolated.run_training_resume
                        with self.assertRaisesRegex(ValueError,'still active'):reviewer(root,record['id'])
                        process.kill();process.communicate(timeout=10)
                    finally:
                        if process.poll() is None:process.kill();process.communicate(timeout=10)
                    self.assertTrue(interruptions.recoverable(root,record));visible=interruptions.history(root,source,saved);self.assertIn(record,visible)
                    self.assertEqual(len([r for r in visible if r['original_run_id']==record['original_run_id']]),1)
                    if counter==0:self.assertEqual(record['schema_version'],7 if reference_phase else 6);self.assertEqual(record['recorded_training_updates'],0);self.assertEqual(record['checkpoint_restored_steps'],0)
                    self.assertFalse((root/'decoder-corpus-run-cancellation-requests'/f'{token}.json').exists())
                    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    with patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):runner(root,record['id'],False,None)
                        spawn.assert_not_called()
                    resumed=runner(root,record['id'],True,reviewer(root,record['id']),uuid.uuid4().hex)
                    if not reference_phase:self.assertEqual(resumed['training_steps_carried'],counter);self.assertEqual(resumed['training_updates_executed'],40-counter)
                    self.assertEqual(resumed['reference_updates_executed'],40-counter if reference_phase else 0)
                    self.assertEqual(resumed['completed_steps'],40);self.assertLessEqual(resumed['checkpoint_parameter_max_error'],1e-7);self.assertLessEqual(resumed['checkpoint_optimizer_max_error'],1e-7)
                    self.assertEqual(training.read(root,resumed['id']),resumed);self.assertEqual(training.read(root,record['id']),record)
                    self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                    path=path.parent/'optimizer.json';original=path.read_bytes();data=json.loads(original);data['step']+=1;path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):training.read(root,record['id'])
                    path.write_bytes(original)

    def test_completed_origins_are_not_offered_as_interrupted(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root)
            record=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
            checkpoints=list((root/interruptions.DIRECTORY).glob('*/record.json'));self.assertEqual(len(checkpoints),8)
            retained=training.read(root,checkpoints[0].parent.name)
            self.assertEqual(retained['original_run_id'],record['id']);self.assertEqual(interruptions.history(root,source,saved),[])
            reviewer=isolated.review_reference_resume if retained['cancellation_phase']=='reference_verification' else isolated.review_training_resume
            with self.assertRaisesRegex(ValueError,'terminal result'):reviewer(root,retained['id'])

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


class LatestCheckpointTest(unittest.TestCase):
    def test_latest_counter_wins_even_with_clock_regression_and_conflicts_are_rejected(self):
        from copy import deepcopy
        early={'id':'a','original_run_id':'origin','completed_steps':0,'created_at':'2026-11-21','review':{'revision':'approval'},'owner_process_id':123,'cancellation_phase':'checkpointed_training'}
        reference={**early,'id':'reference','created_at':'2026-11-22','cancellation_phase':'reference_verification'}
        self.assertEqual(interruptions.latest([early,reference]),[early])
        reference_midpoint={**reference,'id':'reference-midpoint','completed_steps':20}
        self.assertEqual(interruptions.latest([reference,reference_midpoint]),[reference_midpoint])
        self.assertEqual(interruptions.latest([early,reference_midpoint]),[early])
        midpoint={**early,'id':'b','completed_steps':20,'created_at':'2026-11-20'}
        other={**early,'id':'c','original_run_id':'other'}
        self.assertEqual(interruptions.latest([midpoint,early,other]),[midpoint,other])
        for key in ('owner_process_id','review'):
            conflict=deepcopy(early);conflict[key]=456 if key=='owner_process_id' else {'revision':'different'}
            with self.assertRaises(ValueError):interruptions.latest([early,conflict])
