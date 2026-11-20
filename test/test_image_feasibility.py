from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import image_feasibility as feasibility,image_recipe,recipe_contracts,run_manifest


class ImageFeasibilityTests(unittest.TestCase):
    def test_shape_report_is_readonly_binds_approval_and_rechecks_resources(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);rows=image_recipe.dataset();before=deepcopy(rows)
            job={'id':'e'*32,'recipe':'text_to_image','mode':'local','recipe_contract':recipe_contracts.recipe_contract('text_to_image')};settings={'target':.8,'idle':False}
            report=feasibility.review(root,job,rows,settings)
            self.assertTrue(report['feasible']);self.assertFalse(report['hardware']['accelerator_required']);self.assertEqual(report['hardware']['training_device'],'CPU')
            self.assertEqual(report['estimates']['model_scalar_count'],9*48*48+15);self.assertEqual(report['estimates']['gram_matrix_layout_bytes'],0)
            self.assertEqual(rows,before);self.assertEqual(list(root.iterdir()),[])
            with patch.object(feasibility.training_resources,'available_memory',return_value=1):
                with self.assertRaisesRegex(ValueError,'blocked'):feasibility.admit(root,job,rows,settings,report)
            changed=deepcopy(rows);changed[0]['text']='different'
            with self.assertRaises(ValueError):feasibility.admit(root,job,changed,settings,report)
            job.update(image_feasibility=report,image_execution_feasibility=report)
            manifest={'job_id':job['id'],'dataset':{'sha256':run_manifest.digest(rows)}}
            saved=feasibility.attach_manifest(job,manifest);self.assertEqual(saved['image_hardware']['approval'],report)
            saved['image_hardware']['approval']['hardware']['training_device']='GPU'
            with self.assertRaises(ValueError):feasibility.validate_manifest(saved)

    def test_caption_ridge_budget_accounts_for_quadratic_gram_and_dense_pixels(self):
        with TemporaryDirectory() as temporary:
            job={'id':'f'*32,'recipe':'text_to_image','mode':'web_images','recipe_contract':recipe_contracts.recipe_contract('text_to_image')}
            rows=[{'text':'red local caption','split':'train'} for _ in range(12)]+[{'text':'held out caption','split':'test'}]
            report=feasibility.review(Path(temporary),job,rows,{'target':.8,'idle':False})
            self.assertEqual(report['estimates']['gram_matrix_layout_bytes'],12*12*8)
            self.assertEqual(report['estimates']['model_scalar_count'],4*48*48*3)
            self.assertFalse(report['estimates']['measured']);self.assertIsNone(report['estimates']['duration_estimate_seconds'])
