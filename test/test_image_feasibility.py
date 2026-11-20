from copy import deepcopy
import base64
import io
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import image_feasibility as feasibility,image_recipe,recipe_contracts,run_manifest
from PIL import Image


def encoded_image(size=(48,48),mode='RGB'):
    stream=io.BytesIO();Image.new(mode,size).save(stream,format='PNG')
    return base64.b64encode(stream.getvalue()).decode('ascii')


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
            rows=[{'text':'red local caption','split':'train','image':encoded_image()} for _ in range(12)]+[{'text':'held out caption','split':'test','image':encoded_image()}]
            report=feasibility.review(Path(temporary),job,rows,{'target':.8,'idle':False})
            self.assertEqual(report['estimates']['gram_matrix_layout_bytes'],12*12*8)
            self.assertEqual(report['estimates']['model_scalar_count'],4*48*48*3)
            self.assertFalse(report['estimates']['measured']);self.assertIsNone(report['estimates']['duration_estimate_seconds'])

    def test_unprepared_caption_images_and_missing_shape_coverage_reject_before_admission(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);job={'id':'b'*32,'recipe':'text_to_image','mode':'web_images','recipe_contract':recipe_contracts.recipe_contract('text_to_image')};settings={'target':.8,'idle':False}
            oversized=bytearray(base64.b64decode(encoded_image()));oversized[16:24]=struct.pack('>II',100000,100000);oversized[29:33]=struct.pack('>I',zlib.crc32(oversized[12:29]))
            for image in (encoded_image((49,48)),encoded_image(mode='L'),'not base64',base64.b64encode(oversized).decode('ascii')):
                rows=[{'text':'local training caption','split':'train','image':image},{'text':'local test caption','split':'test','image':encoded_image()}]
                with self.assertRaisesRegex(ValueError,'prepared 48x48 RGB PNG'):feasibility.review(root,job,rows,settings)
            job['mode']='local';rows=image_recipe.dataset();rows=[row for row in rows if not(row['shape']=='circle' and row['position']=='left' and row['split']=='train')]
            with self.assertRaisesRegex(ValueError,'every shape/position'):feasibility.review(root,job,rows,settings)
            self.assertEqual(list(root.iterdir()),[])
