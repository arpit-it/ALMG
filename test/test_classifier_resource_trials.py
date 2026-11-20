import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import classifier_resource_trials as trials,classifier_feasibility as feasibility,recipe_contracts


class ClassifierResourceTrialTests(unittest.TestCase):
    def fixture(self,root):
        job={'id':'a'*32,'recipe':'classifier','mode':'local','plan':{'labels':['fruit','space']},'recipe_contract':recipe_contracts.recipe_contract('classifier')}
        rows=[{'text':f'{word} orchard example{i}' if label=='fruit' else f'{word} galaxy example{i}','label':label,'group':f'{label}-{i}'}
              for label,word in [('fruit','apple'),('space','telescope')] for i in range(24)]
        settings={'target':.8,'idle':False,'allow_repair':False};directory=root/'training-sessions'/job['id'];directory.mkdir(parents=True)
        (directory/'dataset.json').write_text(json.dumps(rows));return job,rows,settings,feasibility.review(root,job,rows,settings)

    def test_real_isolated_trial_discards_models_preserves_inputs_and_reopens_evidence(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);job,rows,settings,approved=self.fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=trials.run(root,job,rows,settings,True,approved);observed=result['measurements']
            self.assertNotEqual(observed['process_id'],os.getpid());self.assertTrue(observed['isolated_process']);self.assertFalse(observed['weights_retained'])
            self.assertGreater(observed['process_peak_rss_bytes'],0);self.assertGreater(observed['fit_and_validation_seconds'],0)
            self.assertFalse(result['training_approved']);self.assertFalse(result['release_approved'])
            self.assertTrue(all(p.read_bytes()==value for p,value in before.items()));self.assertFalse(list(root.rglob('*.joblib')))
            self.assertEqual(trials.read(root,job['id'])['records'],[result])
            path=trials._folder(root,job['id'])/(result['id']+'.json');path.write_text(path.read_text().replace('"weights_retained": false','"weights_retained": true'))
            self.assertEqual(trials.read(root,job['id'])['records'],[])

    def test_consent_failure_and_timeout_create_no_trial_report_or_model(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);job,rows,settings,approved=self.fixture(root)
            with self.assertRaises(ValueError):trials.run(root,job,rows,settings,False,approved)
            with self.assertRaises(ValueError):trials.run(root,job,rows,settings,True,None)
            with patch.object(feasibility,'admit',return_value=approved),patch.object(trials.subprocess,'run') as worker:
                worker.return_value=subprocess.CompletedProcess([],1,json.dumps({'error':'fixture failure'}))
                with self.assertRaises(ValueError):trials.run(root,job,rows,settings,True,approved)
                worker.side_effect=subprocess.TimeoutExpired('worker',120)
                with self.assertRaisesRegex(ValueError,'timed out'):trials.run(root,job,rows,settings,True,approved)
            self.assertFalse(trials._folder(root,job['id']).exists());self.assertFalse(list(root.rglob('*.joblib')))
