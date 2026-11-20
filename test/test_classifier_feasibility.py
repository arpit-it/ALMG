from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import classifier_feasibility as feasibility,recipe_contracts,run_manifest


class ClassifierFeasibilityTests(unittest.TestCase):
    def fixture(self):
        return ({'id':'c'*32,'recipe':'classifier','plan':{'labels':['fruit','space']},'recipe_contract':recipe_contracts.recipe_contract('classifier')},
                [{'text':'orchard apple','label':'fruit'},{'text':'galaxy star','label':'space'}],{'target':.8,'idle':False,'allow_repair':False})

    def test_cpu_report_is_readonly_and_requires_no_accelerator(self):
        with TemporaryDirectory() as temporary:
            job,rows,settings=self.fixture();root=Path(temporary)
            report=feasibility.review(root,job,rows,settings)
            self.assertTrue(report['feasible']);self.assertFalse(report['hardware']['accelerator_required'])
            self.assertEqual(report['hardware']['training_device'],'CPU');self.assertFalse(report['estimates']['measured'])
            self.assertEqual(list(root.iterdir()),[])
            changed=deepcopy(report);changed['settings']['target']=.9
            with self.assertRaises(ValueError):feasibility.admit(root,job,rows,settings,changed)
            with patch.object(feasibility.training_resources,'available_memory',return_value=1):
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.admit(root,job,rows,settings,report)

    def test_manifest_snapshots_bind_prepared_approval_not_postsplit_rows_and_reject_tampering(self):
        with TemporaryDirectory() as temporary:
            job,rows,settings=self.fixture();root=Path(temporary);report=feasibility.review(root,job,rows,settings)
            job['classifier_feasibility']=report;job['classifier_execution_feasibility']=report
            manifest={'job_id':job['id'],'dataset':{'sha256':'post-split-digest'},'approval':{'binding':{'prepared_dataset_sha256':run_manifest.digest(rows)}}}
            saved=feasibility.attach_manifest(job,manifest);self.assertEqual(saved['classifier_hardware']['approval'],report)
            saved['classifier_hardware']['approval']['hardware']['training_device']='GPU'
            with self.assertRaises(ValueError):feasibility.validate_manifest(saved)
            self.assertEqual(feasibility.validate_manifest(manifest),manifest)
