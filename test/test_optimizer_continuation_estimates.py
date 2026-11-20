from copy import deepcopy
import unittest
from backend import decoder_optimizer_continuation_estimates as feedback
from backend.run_manifest import digest


class ContinuationFeedbackTests(unittest.TestCase):
    def current(self):
        return {'source':{'record_id':'parent','checkpoint_step':10,'optimizer_sha256':'moments'},'config':{'steps':20},'runtime':{'python':'fixture'},'implementation_sha256':'producer'}
    def record(self,current,seconds=2.,identifier='a'):
        record={'format':'almg-optimizer-continuation-v1','schema_version':1,'id':identifier*32,'review':deepcopy(current),'training_approved':True,'source_modified':False,'restored_steps':10,'completed_steps':20,'scheduler_completed_steps':20,
            'isolated_workflow_measurements':{'format':'almg-isolated-optimizer-continuation-measurements-v1','schema_version':1,'scope':'fresh_process_optimizer_checkpoint_continuation','measured':True,'isolated_trial_peak_measured':True,'elapsed_seconds':seconds,'isolated_process_peak_rss_bytes':200,'isolated_metal_peak_bytes':100}}
        record['revision']=digest(record);return record

    def test_exact_checkpoint_feedback_has_separate_memory_floor_and_remaining_work_headroom(self):
        current=self.current();a=self.record(current);b=self.record(current,4.,'b');memory,work=feedback.feedback([a,b],current)
        self.assertEqual(memory['calculated_memory_floor_bytes'],375);self.assertTrue(memory['measured'])
        self.assertEqual(work['estimated_seconds'],5.);self.assertFalse(work['measured']);self.assertEqual(work['sample_count'],2)
        self.assertEqual(work['source_records'][0]['record_revision'],a['revision'])
        for key,value in [('source',{'record_id':'other','checkpoint_step':10}),('source',{**current['source'],'optimizer_sha256':'changed'}),('config',{'steps':10}),('runtime',{'python':'other'}),('implementation_sha256','other')]:
            self.assertEqual(feedback.feedback([a],{**current,key:value}),(None,None))

    def test_nonisolated_incomplete_or_malformed_feedback_is_ignored(self):
        current=self.current()
        for key,value in [('status','canceled'),('restored_steps',5),('completed_steps',10),('scheduler_completed_steps',10),('source_modified',True)]:
            record=self.record(current);record[key]=value;record['revision']=digest({k:v for k,v in record.items() if k!='revision'});self.assertEqual(feedback.feedback([record],current),(None,None))
        for key,value in [('scope','fresh_process_bounded_optimizer_fixture'),('isolated_trial_peak_measured',False),('elapsed_seconds',0),('isolated_process_peak_rss_bytes',True),('isolated_metal_peak_bytes',-1)]:
            record=self.record(current);record['isolated_workflow_measurements'][key]=value;record['revision']=digest({k:v for k,v in record.items() if k!='revision'});self.assertEqual(feedback.feedback([record],current),(None,None))
        record=self.record(current);record['revision']='tampered';self.assertEqual(feedback.feedback([record],current),(None,None))
