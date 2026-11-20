from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_phase_feedback as feedback, decoder_corpus_optimizer as training, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


def sample(phase):
    key='reference_resume_from' if phase=='reference_resume' else 'training_resume_from'
    review={'format':phase,'schema_version':1,'scope':phase,'source':{'initialization_id':'a'*32},key:{'record_id':'b'*32,'record_revision':'saved','completed_steps':2},
            'corpus_id':'c'*32,'corpus_revision':'corpus','config':{'steps':20},'model_config':{'hidden':8},'runtime':{'machine':'arm64'},'implementation_sha256':'producer','execution_mode':'fresh_process'}
    record={'id':'d'*32,'review':deepcopy(review),'status':'completed','training_approved':True,'release_approved':False,'completed_steps':20,'scheduler_completed_steps':20,'checkpoint_restored_steps':10,
            'reference_steps_carried':2 if phase=='reference_resume' else 20,'reference_updates_executed':18 if phase=='reference_resume' else 0,
            'isolated_workflow_measurements':{'format':'almg-isolated-corpus-'+('reference' if phase=='reference_resume' else 'training')+'-resume-measurements-v1','schema_version':1,'scope':'fresh_process_corpus_'+phase,
              'action':phase,'measured':True,'isolated_trial_peak_measured':True,'process_id':100,'elapsed_seconds':2.,'isolated_process_peak_rss_bytes':1000,'isolated_metal_peak_bytes':100}}
    if phase=='training_resume':record.update(training_steps_carried=2,training_updates_executed=18)
    record['revision']=training.digest(record)
    return review,record


class PhaseFeedbackTest(unittest.TestCase):
    def test_exact_phase_source_and_work_only_with_conservative_maxima(self):
        for phase in ('reference_resume','training_resume'):
            current,record=sample(phase);other=deepcopy(record);other['id']='e'*32;other['isolated_workflow_measurements'].update(elapsed_seconds=3.,isolated_process_peak_rss_bytes=900,isolated_metal_peak_bytes=200);other['revision']=training.digest({k:v for k,v in other.items() if k!='revision'})
            memory,work=feedback.feedback([record,other],current,phase)
            self.assertEqual(work['sample_count'],2);self.assertEqual(work['estimated_seconds'],3.75);self.assertFalse(work['measured'])
            self.assertEqual(memory['calculated_memory_floor_bytes'],1500);self.assertEqual(memory['phase'],phase)
            for mutate in (lambda r:r.update(status='canceled'),lambda r:r.update(training_approved=False),lambda r:r.update(completed_steps=19),lambda r:r.update(reference_updates_executed=17),
                           lambda r:r['review'].update(execution_mode='shared_backend'),lambda r:r['review'].update(implementation_sha256='other'),lambda r:r['review'].update(runtime={'machine':'other'}),
                           lambda r:r['review'].update(config={'steps':10}),lambda r:r['review'].update(corpus_revision='other'),lambda r:r['isolated_workflow_measurements'].update(action='full'),
                           lambda r:r['isolated_workflow_measurements'].update(elapsed_seconds=float('nan'))):
                changed=deepcopy(record);mutate(changed)
                try:changed['revision']=training.digest({k:v for k,v in changed.items() if k!='revision'})
                except ValueError:pass
                self.assertEqual(feedback.feedback([changed],current,phase),(None,None))
            key='reference_resume_from' if phase=='reference_resume' else 'training_resume_from'
            for key2,value in (('record_id','f'*32),('record_revision','other'),('completed_steps',3)):
                changed=deepcopy(current);changed[key][key2]=value
                self.assertEqual(feedback.feedback([record],changed,phase),(None,None))
            other_phase='training_resume' if phase=='reference_resume' else 'reference_resume';_,incompatible=sample(other_phase)
            self.assertEqual(feedback.feedback([incompatible],current,phase),(None,None))

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires isolated exact-phase corpus profiling')
    def test_real_phase_feedback_excludes_cancellation_and_other_retained_sources_and_blocks_before_spawn(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root);original=training.optimizer.update
            for phase,target in (('reference_resume',1),('training_resume',31)):
                approved=training.review(root,source,saved,c);token=uuid.uuid4().hex;calls=0
                def stop(*args):
                    nonlocal calls
                    result=original(*args);calls+=1
                    if calls==target:training.run_cancellation.request(root,approved,token,True)
                    return result
                with patch.object(training.optimizer,'update',side_effect=stop):parent=training.run(root,True,source,saved,c,approved,request_id=token)
                reviewer=isolated.review_reference_resume if phase=='reference_resume' else isolated.review_training_resume
                runner=isolated.run_reference_resume if phase=='reference_resume' else isolated.run_training_resume
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                first=reviewer(root,parent['id']);self.assertIsNone(first['estimates']['phase_resume_work_estimate'])
                early=uuid.uuid4().hex;training.run_cancellation.request(root,first,early,True);canceled=runner(root,parent['id'],True,first,early)
                self.assertEqual(canceled['status'],'canceled');self.assertIsNone(reviewer(root,parent['id'])['estimates']['phase_resume_work_estimate'])
                record=runner(root,parent['id'],True,reviewer(root,parent['id']),uuid.uuid4().hex);updated=reviewer(root,parent['id']);est=updated['estimates'];observed=record['isolated_workflow_measurements']
                self.assertEqual(est['phase_resume_work_estimate']['estimated_seconds'],observed['elapsed_seconds']*1.25)
                self.assertEqual(est['phase_resume_work_estimate']['source_records'][0]['record_id'],record['id'])
                self.assertGreaterEqual(est['required_available_memory_bytes'],est['calculated_memory_reserve_bytes']);self.assertGreaterEqual(est['required_available_memory_bytes'],est['isolated_phase_resume_memory']['calculated_memory_floor_bytes'])
                self.assertIsNone(reviewer(root,canceled['id'])['estimates']['phase_resume_work_estimate'])
                self.assertIsNone(isolated.review(root,source,saved,c)['estimates']['corpus_work_estimate'])
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                profile={**updated['hardware'],'available_memory_bytes':est['required_available_memory_bytes']+1024}
                with patch.object(training.hardware,'hardware',return_value=profile),patch.object(feedback,'feedback',return_value=({'calculated_memory_floor_bytes':profile['available_memory_bytes']+1024},None)):
                    blocked=reviewer(root,parent['id']);self.assertFalse(blocked['feasible'])
                    with patch.object(isolated,'review_reference_resume' if phase=='reference_resume' else 'review_training_resume',return_value=blocked),patch.object(isolated.subprocess,'Popen') as spawn:
                        with self.assertRaises(ValueError):runner(root,parent['id'],True,blocked,uuid.uuid4().hex)
                        spawn.assert_not_called()
