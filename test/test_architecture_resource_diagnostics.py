from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_architecture_feasibility as feasibility
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations
from test_architecture_feasibility import hardware


class ArchitectureResourceDiagnosticsTest(unittest.TestCase):
    def test_each_reserve_shortfall_and_calibrated_metal_peak(self):
        profile = hardware()
        profile.update(available_memory_bytes=0, free_disk_bytes=5)
        profile['metal_device']['max_recommended_working_set_size'] = 8
        estimates = {'required_available_memory_bytes': 3, 'required_free_disk_bytes': 5,
                     'estimated_gpu_working_bytes': 4, 'calibrated_gpu_working_bytes': 10}
        result = feasibility.resource_diagnostics(profile, estimates)
        self.assertEqual([c['shortfall_bytes'] for c in result['checks']], [3, 0, 2])
        self.assertEqual([c['resource'] for c in result['shortfalls']], ['memory', 'metal_working_set'])
        self.assertFalse(feasibility._fits(profile, estimates))
        profile['available_memory_bytes'] = 3
        profile['metal_device']['max_recommended_working_set_size'] = 10
        self.assertTrue(feasibility._fits(profile, estimates))
        self.assertEqual(feasibility.resource_diagnostics(profile, estimates)['shortfalls'], [])

    def test_unknown_recommendation_is_not_reported_as_a_fit(self):
        estimates = {'required_available_memory_bytes': 1, 'required_free_disk_bytes': 1,
                     'estimated_gpu_working_bytes': 4}
        for value in (None, True, -1, '10', 1.5):
            with self.subTest(value=value):
                profile = hardware()
                profile['metal_device'] = {'max_recommended_working_set_size': value}
                check = feasibility.resource_diagnostics(profile, estimates)['checks'][2]
                self.assertIsNone(check['available_bytes'])
                self.assertIsNone(check['fits'])
                self.assertIsNone(check['shortfall_bytes'])
                self.assertEqual(check['enforced'], type(value) is int)
        profile['metal_device'] = {}
        self.assertTrue(feasibility._fits(profile, estimates))
        self.assertEqual(feasibility.resource_diagnostics(profile, estimates)['unknown_resources'], ['metal_working_set'])

    def test_report_uses_one_snapshot_and_keeps_independent_blockers_readonly(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = plans.save(root, True, plans.review({**plans.DEFAULT, 'vocab_size': 4}))
            source = initializations.run(root, plan['id'], True, plan)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            profile = hardware()
            with patch.object(feasibility, 'hardware', return_value=profile) as probe:
                report = feasibility.review(root, plan['id'], True, source, device='cpu')
            probe.assert_called_once_with(root)
            self.assertFalse(report['feasible'])
            self.assertTrue(report['blockers'])
            self.assertFalse(report['training_approved'])
            self.assertEqual(report['resource_diagnostics']['shortfalls'], [])
            self.assertEqual(report['resource_diagnostics']['observed_at'], profile['observed_at'])
            self.assertEqual(report['revision'], feasibility.digest({k:v for k,v in report.items() if k!='revision'}))
            self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
