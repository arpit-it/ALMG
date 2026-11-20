import base64
import io
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from backend import image_resource_trials as trials,image_feasibility as feasibility,image_recipe,recipe_contracts


class ImageResourceTrialTests(unittest.TestCase):
    def fixture(self,root,mode):
        job={'id':'a'*32,'recipe':'text_to_image','mode':mode,'recipe_contract':recipe_contracts.recipe_contract('text_to_image')}
        if mode=='local':rows=image_recipe.dataset()
        else:
            stream=io.BytesIO();Image.new('RGB',(48,48),(220,60,70)).save(stream,format='PNG');encoded=base64.b64encode(stream.getvalue()).decode('ascii')
            rows=[{'text':f'red tile example {i}','split':'train' if i<12 else 'test','image':encoded} for i in range(15)]
        settings={'target':.8,'idle':False};directory=root/'training-sessions'/job['id'];directory.mkdir(parents=True)
        (directory/'dataset.json').write_text(json.dumps(rows));return job,rows,settings,feasibility.review(root,job,rows,settings)

    def test_both_real_isolated_image_variants_discard_weights_and_preserve_prepared_files(self):
        for mode in ('local','web_images'):
            with self.subTest(mode=mode),TemporaryDirectory() as temporary:
                root=Path(temporary);job,rows,settings,approved=self.fixture(root,mode);path=root/'training-sessions'/job['id']/'dataset.json';before=path.read_bytes()
                record=trials.run(root,job,rows,settings,True,approved);observed=record['measurements']
                self.assertNotEqual(observed['process_id'],os.getpid());self.assertTrue(observed['isolated_process']);self.assertFalse(observed['weights_retained'])
                self.assertGreater(observed['process_peak_rss_bytes'],0);self.assertGreater(observed['fit_and_validation_seconds'],0)
                self.assertEqual(record['variant'],approved['variant']);self.assertEqual(record['mode'],mode)
                self.assertEqual(record['admission']['dataset_sha256'],approved['dataset_sha256']);self.assertFalse(record['training_approved']);self.assertFalse(record['release_approved'])
                self.assertEqual(path.read_bytes(),before)
                self.assertEqual({p.suffix for p in root.rglob('*') if p.is_file()},{'.json'})
                self.assertEqual(trials.read(root,job['id'])['records'],[record])
                saved=trials._folder(root,job['id'])/(record['id']+'.json');saved.write_text(saved.read_text().replace('"weights_retained": false','"weights_retained": true'))
                self.assertEqual(trials.read(root,job['id'])['records'],[])

    def test_consent_stale_input_failure_and_timeout_save_no_report(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);job,rows,settings,approved=self.fixture(root,'local')
            with self.assertRaises(ValueError):trials.run(root,job,rows,settings,False,approved)
            with self.assertRaises(ValueError):trials.run(root,job,rows,settings,True,None)
            with self.assertRaisesRegex(ValueError,'review changed'):trials.run(root,job,rows,{**settings,'target':.9},True,approved)
            with patch.object(feasibility,'admit',return_value=approved),patch.object(trials.subprocess,'run') as worker:
                worker.return_value=subprocess.CompletedProcess([],1,json.dumps({'error':'fixture failure'}))
                with self.assertRaises(ValueError):trials.run(root,job,rows,settings,True,approved)
                worker.side_effect=subprocess.TimeoutExpired('worker',120)
                with self.assertRaisesRegex(ValueError,'timed out'):trials.run(root,job,rows,settings,True,approved)
            self.assertFalse(trials._folder(root,job['id']).exists())
            self.assertEqual(len(list(root.rglob('*.json'))),1)
