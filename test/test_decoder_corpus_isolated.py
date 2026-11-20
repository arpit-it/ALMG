from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from backend import decoder_corpus_isolated as isolated, decoder_corpus_feedback as feedback
from test_decoder_corpus_optimizer import corpus


class CorpusIsolationTest(unittest.TestCase):
    def test_no_consent_stale_review_and_peak_floor_cannot_start_worker(self):
        training=isolated.training
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root)
            profile={'system':'Darwin','machine':'arm64','metal_available':True,'metal_device':{},'available_memory_bytes':8*1024**3,'free_disk_bytes':8*1024**3,'errors':[]}
            with patch.object(training.hardware,'hardware',return_value=profile):
                approved=isolated.review(root,source,saved,settings)
                with patch.object(isolated.subprocess,'Popen') as spawn:
                    with self.assertRaises(ValueError):isolated.run(root,False,source,saved,settings,approved)
                    changed=deepcopy(approved);changed['corpus_revision']='changed'
                    with self.assertRaises(ValueError):isolated.run(root,True,source,saved,settings,changed)
                    spawn.assert_not_called()
                base=approved['estimates']['required_available_memory_bytes'];profile['available_memory_bytes']=base+512*1024
                with patch.object(training.feedback,'feedback',return_value=({'calculated_memory_floor_bytes':base+1024*1024},None)):
                    blocked=isolated.review(root,source,saved,settings)
                    self.assertFalse(blocked['feasible']);self.assertEqual(blocked['estimates']['calculated_memory_reserve_bytes'],base)
                    self.assertEqual(blocked['estimates']['required_available_memory_bytes'],base+1024*1024)
                    with patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):isolated.run(root,True,source,saved,settings,blocked)
                        spawn.assert_not_called()
            self.assertFalse((root/'decoder-corpus-optimizer-runs').exists())

    def test_feedback_never_crosses_corpus_configuration_runtime_or_producer(self):
        current={'source':{'id':'init'},'corpus_id':'corpus','corpus_revision':'revision','config':{'steps':20,'compute_precision':'float32'},'model_config':{'seed':7},'runtime':{'mlx':'local'},'implementation_sha256':'code','execution_mode':'fresh_process'}
        record={'id':'run','review':deepcopy(current),'completed_steps':20,'scheduler_completed_steps':20,'checkpoint_restored_steps':10,'training_approved':True,
                'isolated_workflow_measurements':{'format':'almg-isolated-corpus-optimizer-measurements-v1','schema_version':1,'scope':'fresh_process_reviewed_corpus_optimizer','measured':True,'isolated_trial_peak_measured':True,'process_id':123,'elapsed_seconds':2.,'isolated_process_peak_rss_bytes':1000,'isolated_metal_peak_bytes':100}}
        record['revision']=isolated.training.digest(record)
        memory,work=feedback.feedback([record],current)
        self.assertEqual(memory['calculated_memory_floor_bytes'],1375);self.assertEqual(work['estimated_seconds'],2.5)
        for key,value in (('corpus_id','different'),('corpus_revision','different'),('runtime',{'mlx':'other'}),('implementation_sha256','new'),('config',{'steps':10}),('execution_mode','shared_backend')):
            changed={**current,key:value};self.assertEqual(feedback.feedback([record],changed),(None,None))
        changed=deepcopy(record);changed['isolated_workflow_measurements']['elapsed_seconds']=float('inf')
        self.assertEqual(feedback.feedback([changed],current),(None,None))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires isolated Metal corpus training')
    def test_real_workers_save_peaks_and_feed_only_exact_compatible_review(self):
        training=isolated.training
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,settings=corpus(root)
            before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
            for kind,precision in (('sgd','float32'),('adamw','mixed_float16')):
                c={**settings,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'batch_size':2,'gradient_accumulation_steps':2,'compute_precision':precision,'loss_scale':128. if precision=='mixed_float16' else 1.}
                approved=isolated.review(root,source,saved,c)
                self.assertIsNone(approved['estimates']['corpus_work_estimate'])
                record=isolated.run(root,True,source,saved,c,approved);observed=record['isolated_workflow_measurements']
                self.assertNotEqual(observed['process_id'],os.getpid())
                self.assertTrue(observed['isolated_trial_peak_measured']);self.assertGreater(observed['elapsed_seconds'],0.)
                self.assertGreater(observed['isolated_process_peak_rss_bytes'],0);self.assertGreater(observed['isolated_metal_peak_bytes'],0)
                self.assertEqual(training.read(root,record['id']),record);self.assertLess(record['final_losses']['train'],record['initial_losses']['train'])
                refreshed=isolated.review(root,source,saved,c);est=refreshed['estimates']
                self.assertEqual(est['corpus_work_estimate']['estimated_seconds'],observed['elapsed_seconds']*1.25)
                self.assertEqual(est['isolated_corpus_memory']['source_records'][0]['record_id'],record['id'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],est['calculated_memory_reserve_bytes'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],est['isolated_corpus_memory']['calculated_memory_floor_bytes'])
                other=isolated.review(root,source,saved,{**c,'steps':10});self.assertIsNone(other['estimates']['corpus_work_estimate'])
                shared=training.review(root,source,saved,c);self.assertIsNone(shared['estimates']['corpus_work_estimate'])
                self.assertTrue(all(path.read_bytes()==data for path,data in before.items()))
                with patch.object(isolated,'review',return_value=approved),patch.object(isolated.subprocess,'Popen') as spawn:
                    process=Mock(pid=observed['process_id'],returncode=0);spawn.return_value=process
                    process.communicate.return_value=('{"nonce":"wrong","record_id":"'+record['id']+'","process_id":'+str(process.pid)+'}','')
                    with self.assertRaises(ValueError):isolated.run(root,True,source,saved,c,approved)
