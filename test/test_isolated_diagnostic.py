import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_architecture_backward as backward,decoder_architecture_plans as plans,decoder_architecture_initializations as initializations


class IsolatedDiagnosticTests(unittest.TestCase):
    def fixture(self,root):
        plan=plans.save(root,True,plans.review(dict(plans.DEFAULT)))
        return initializations.run(root,plan['id'],True,plan)

    def test_no_worker_without_consent_and_failed_workers_never_publish(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root)
            with patch.object(backward.subprocess,'run') as worker:
                with self.assertRaises(ValueError):backward.run_isolated(root,record['plan_id'],False,record)
                worker.assert_not_called()
            with patch.object(backward.feasibility,'admit'),patch.object(backward.subprocess,'run') as worker:
                for result in (subprocess.CompletedProcess([],1,json.dumps({'error':'fixture failure'})),subprocess.CompletedProcess([],0,'invalid'),subprocess.CompletedProcess([],0,'{}')):
                    worker.return_value=result
                    with self.assertRaises(ValueError):backward.run_isolated(root,record['plan_id'],True,record)
                worker.side_effect=subprocess.TimeoutExpired('worker',120)
                with self.assertRaisesRegex(ValueError,'timed out'):backward.run_isolated(root,record['plan_id'],True,record)
            self.assertFalse(backward._folder(root,record['plan_id']).exists())

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real Metal autodiff')
    def test_fresh_worker_reports_isolated_peak_and_preserves_source(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=backward.run_isolated(root,record['plan_id'],True,record);m=report['diagnostic_measurements']
            self.assertNotEqual(m['isolated_process_id'],os.getpid());self.assertTrue(m['isolated_trial_peak_measured'])
            self.assertGreater(m['isolated_metal_peak_bytes'],0);self.assertGreater(m['isolated_process_peak_rss_bytes'],0)
            self.assertGreaterEqual(m['conservative_observed_gpu_budget_bytes'],m['isolated_metal_peak_bytes'])
            self.assertGreater(m['isolated_workflow_elapsed_seconds'],m['elapsed_seconds'])
            self.assertEqual(backward.list_reports(root,record['plan_id'],True),[report])
            self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))
