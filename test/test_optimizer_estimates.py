from copy import deepcopy
import unittest
import math
from backend import decoder_optimizer_estimates as estimates
from backend.run_manifest import digest


class OptimizerEstimateTests(unittest.TestCase):
    def current(self):
        return {'source':{'initialization_id':'fresh','model_sha256':'weights'},'config':{'steps':20},'model_config':{'layers':2},'runtime':{'python':'fixture'},'implementation_sha256':'producer'}

    def record(self,current,seconds=2.,identifier='a'):
        record={'id':identifier*32,'review':deepcopy(current),'optimizer':deepcopy(current['config']),'training_approved':True,'completed_steps':20,'scheduler_completed_steps':20,'checkpoint_restored_steps':10,
            'workflow_measurements':{'format':'almg-optimizer-workflow-measurements-v1','schema_version':1,'scope':'bounded_optimizer_fixture_in_shared_backend','measured':True,'elapsed_seconds':seconds}}
        record['revision']=digest(record);return record

    def test_highest_verified_compatible_work_time_gets_headroom_without_memory_claims(self):
        current=self.current();a=self.record(current);b=self.record(current,4.,'b')
        result=estimates.estimate([a,b],current)
        self.assertEqual(result['estimated_seconds'],5.);self.assertEqual(result['sample_count'],2);self.assertFalse(result['measured'])
        self.assertEqual(result['observed_min_seconds'],2.);self.assertEqual(result['observed_max_seconds'],4.)
        self.assertEqual(result['source_records'][0]['record_revision'],a['revision'])
        self.assertNotIn('required_available_memory_bytes',result)

    def test_changed_initialization_configuration_runtime_or_producer_does_not_reuse_observations(self):
        current=self.current();record=self.record(current)
        for key,value in [('source',{'initialization_id':'other'}),('config',{'steps':10}),('model_config',{'layers':1}),('runtime',{'python':'other'}),('implementation_sha256','changed')]:
            changed={**current,key:value};self.assertIsNone(estimates.estimate([record],changed))
        legacy=deepcopy(record);legacy['review'].pop('runtime');legacy['revision']=digest({k:v for k,v in legacy.items() if k!='revision'})
        self.assertIsNone(estimates.estimate([legacy],current))

    def test_unfinished_tampered_or_nonpositive_nonfinite_observations_are_ignored(self):
        current=self.current()
        for key,value in [('completed_steps',10),('scheduler_completed_steps',10),('checkpoint_restored_steps',5),('training_approved',False)]:
            record=self.record(current);record[key]=value;record['revision']=digest({k:v for k,v in record.items() if k!='revision'})
            self.assertIsNone(estimates.estimate([record],current))
        for seconds in (0.,-1.,True,float('nan'),float('inf')):
            record=self.record(current);record['workflow_measurements']['elapsed_seconds']=seconds
            if math.isfinite(seconds):record['revision']=digest({k:v for k,v in record.items() if k!='revision'})
            self.assertIsNone(estimates.estimate([record],current))
        record=self.record(current);record['revision']='tampered';self.assertIsNone(estimates.estimate([record],current))
