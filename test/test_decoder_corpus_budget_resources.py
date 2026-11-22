from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_corpus_budget as budget
from test_decoder_corpus_optimizer import corpus


class ResourceAdmissionTest(unittest.TestCase):
    def test_thresholds_and_shortfalls(self):
        result = budget.resource_admission({'hardware': {'available_memory_bytes': 0, 'free_disk_bytes': 7, 'metal_device': {'max_recommended_working_set_size': 0}},
            'estimates': {'required_available_memory_bytes': 0, 'required_free_disk_bytes': 10, 'estimated_gpu_working_bytes': 0}})
        self.assertEqual([c['fits'] for c in result['checks']], [True, False, True])
        self.assertEqual(result['shortfalls'][0]['shortfall_bytes'], 3)
        self.assertEqual(result['unknown_resources'], [])

    def test_missing_or_invalid_values_stay_unknown(self):
        for value in (None, True, -1, 1.5, '10'):
            with self.subTest(value=value):
                result = budget.resource_admission({'hardware': {'available_memory_bytes': value},
                    'estimates': {'required_available_memory_bytes': 1}})
                self.assertEqual(result['unknown_resources'], ['memory', 'disk', 'metal_working_set'])
                self.assertIsNone(result['checks'][0]['shortfall_bytes'])
                self.assertEqual(result['shortfalls'], [])

    def test_real_review_uses_same_snapshot_and_preserves_blockers_without_writes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, saved, config = corpus(root)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile = {'system': 'Darwin', 'machine': 'arm64', 'metal_available': True,
                       'metal_device': {}, 'available_memory_bytes': 1, 'free_disk_bytes': 1, 'errors': []}
            with patch.object(budget.training.hardware, 'hardware', return_value=profile), patch.object(budget.isolated, 'run') as run:
                result = budget.review(root, source, saved, config)
            run.assert_not_called()
            self.assertFalse(result['feasible'])
            self.assertTrue(result['blockers'])
            self.assertFalse(result['training_approved'])
            for check in result['resource_admission']['checks']:
                if check['resource']=='metal_working_set':
                    self.assertIsNone(check['available_bytes']);self.assertIsNone(check['fits']);self.assertFalse(check['enforced'])
                else:
                    self.assertEqual(check['available_bytes'], 1)
                    self.assertEqual(check['shortfall_bytes'], check['required_bytes'] - 1)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})


    def test_calibrated_metal_shortfall_and_optional_unknown_match_admission(self):
        hardware={'available_memory_bytes':10,'free_disk_bytes':10,'metal_device':{'max_recommended_working_set_size':5}}
        estimates={'required_available_memory_bytes':1,'required_free_disk_bytes':1,'estimated_gpu_working_bytes':2,'calibrated_gpu_working_bytes':8}
        report=budget.resource_admission({'hardware':hardware,'estimates':estimates})
        self.assertEqual([check['resource'] for check in report['shortfalls']],['metal_working_set'])
        self.assertEqual(report['shortfalls'][0]['shortfall_bytes'],3)
        self.assertEqual(report['shortfalls'][0]['required_bytes'],8)
        self.assertTrue(report['shortfalls'][0]['enforced'])
        self.assertFalse(budget.training.hardware._fits(hardware,estimates))
        for value in (None,True,1.5,'10'):
            with self.subTest(recommendation=value):
                hardware['metal_device']['max_recommended_working_set_size']=value
                report=budget.resource_admission({'hardware':hardware,'estimates':estimates})
                check=next(check for check in report['checks'] if check['resource']=='metal_working_set')
                self.assertIsNone(check['fits']);self.assertIsNone(check['shortfall_bytes']);self.assertFalse(check['enforced'])
                self.assertEqual(report['unknown_resources'],['metal_working_set'])
                self.assertTrue(budget.training.hardware._fits(hardware,estimates))
