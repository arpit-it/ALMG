from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_corpus_budget as budget
from test_decoder_corpus_optimizer import corpus


class ResourceAdmissionTest(unittest.TestCase):
    def test_thresholds_and_shortfalls(self):
        result = budget.resource_admission({'hardware': {'available_memory_bytes': 0, 'free_disk_bytes': 7},
            'estimates': {'required_available_memory_bytes': 0, 'required_free_disk_bytes': 10}})
        self.assertEqual([c['fits'] for c in result['checks']], [True, False])
        self.assertEqual(result['shortfalls'][0]['shortfall_bytes'], 3)
        self.assertEqual(result['unknown_resources'], [])

    def test_missing_or_invalid_values_stay_unknown(self):
        for value in (None, True, -1, 1.5, '10'):
            with self.subTest(value=value):
                result = budget.resource_admission({'hardware': {'available_memory_bytes': value},
                    'estimates': {'required_available_memory_bytes': 1}})
                self.assertEqual(result['unknown_resources'], ['memory', 'disk'])
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
                self.assertEqual(check['available_bytes'], 1)
                self.assertEqual(check['shortfall_bytes'], check['required_bytes'] - 1)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
