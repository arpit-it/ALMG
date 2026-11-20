from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_architecture_feasibility as feasibility,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations,decoder_architecture_backward as backward
from backend.planned_decoder import PlannedDecoder


def hardware():
    return {'system':'Darwin','machine':'arm64','total_memory_bytes':36*1024**3,'available_memory_bytes':24*1024**3,
            'free_disk_bytes':32*1024**3,'metal_available':True,'metal_device':{'device_name':'Fixture Metal','max_recommended_working_set_size':24*1024**3},
            'mlx_version':'fixture','cpu_forward_supported':True,'cpu_backward_fallback':False,'cuda_status':'not_probed','errors':[],'observed_at':'fixture'}


class ArchitectureFeasibilityTests(unittest.TestCase):
    def fixture(self,root):
        config={**plans.DEFAULT,'layers':4,'hidden_size':64,'attention_heads':4,'head_dim':16,'feed_forward_size':256,'context_length':128,'vocab_size':512}
        plan=plans.save(root,True,plans.review(config));return initializations.run(root,plan['id'],True,plan)

    def test_preflight_is_readonly_before_model_allocation_and_separates_estimates(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(feasibility,'hardware',return_value=hardware()),patch.object(PlannedDecoder,'__init__',side_effect=AssertionError('Preflight must not allocate model weights')):
                report=feasibility.review(root,record['plan_id'],True,record)
            self.assertTrue(report['feasible']);self.assertEqual(report['estimates']['parameter_bytes'],1081344)
            self.assertEqual(report['estimates']['optimizer_state_bytes'],0);self.assertEqual(report['estimates']['dataset_storage_bytes'],0)
            self.assertFalse(report['estimates']['measured']);self.assertIsNone(report['estimates']['duration_estimate_seconds'])
            self.assertEqual(set(before),{p for p in root.rglob('*') if p.is_file()});self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))

    def test_low_memory_recommends_smaller_valid_plan_without_changing_original(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root);model=initializations._folder(root,record['plan_id'])/record['id']/'model.json'
            original=feasibility.estimate(record['config'],model.stat().st_size);small={**record['config'],'layers':2}
            new_bytes=plans.review(small)['estimates']['weight_bytes'];json_bytes=(model.stat().st_size*new_bytes+record['actual_weight_bytes']-1)//record['actual_weight_bytes']
            smaller=feasibility.estimate(small,json_bytes);profile=hardware();profile['available_memory_bytes']=(original['required_available_memory_bytes']+smaller['required_available_memory_bytes'])//2
            with patch.object(feasibility,'hardware',return_value=profile):report=feasibility.review(root,record['plan_id'],True,record)
            self.assertFalse(report['feasible']);self.assertIsNotNone(report['recommendation']);self.assertLess(report['recommendation']['config']['layers'],record['config']['layers'])
            self.assertEqual(initializations.read(root,record['plan_id'],record['id']),record)

    def test_unsupported_precision_device_and_unknown_resources_cannot_start(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root)
            with patch.object(feasibility,'hardware',return_value=hardware()),patch.object(backward,'metal_functions') as execute:
                for precision,device in [('float16','metal'),('float32','cpu'),('float32','cuda')]:
                    report=feasibility.review(root,record['plan_id'],True,record,precision,device);self.assertFalse(report['feasible'])
                    with self.assertRaises(ValueError):backward.run(root,record['plan_id'],True,record,report)
                execute.assert_not_called()
            profile=hardware();profile['available_memory_bytes']=None
            with patch.object(feasibility,'hardware',return_value=profile):
                with self.assertRaises(ValueError):feasibility.admit(root,record['plan_id'],record)

    def test_execution_rechecks_live_resources_and_rejects_stale_review(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root)
            with patch.object(feasibility,'hardware',return_value=hardware()):approved=feasibility.review(root,record['plan_id'],True,record)
            low=hardware();low['available_memory_bytes']=1
            with patch.object(feasibility,'hardware',return_value=low):
                with self.assertRaises(ValueError):feasibility.admit(root,record['plan_id'],record,approved)
            stale=deepcopy(approved);stale['source']['model_sha256']='0'*64
            with patch.object(feasibility,'hardware',return_value=hardware()):
                with self.assertRaises(ValueError):feasibility.admit(root,record['plan_id'],record,stale)
