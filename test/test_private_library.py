"""Private imports remain separate from ordinary model candidates/releases."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials, studio


class PrivateLibraryTest(unittest.TestCase):
    def test_private_rows_are_verified_and_corrupt_entries_remain_unavailable(self):
        records = [{'id':'a'*32,'source_name':'good.zip','created_at':'2026-11-19T00:00:00+00:00'},
                   {'id':'b'*32,'source_name':'broken.zip','created_at':'2026-11-19T00:00:00+00:00'}]
        def verify(root, import_id):
            if import_id=='b'*32:raise ValueError('Corrupt bundle')
            return records[0]
        with patch.object(decoder_trials,'list_imports',return_value=records), patch.object(decoder_trials,'read_import',side_effect=verify):
            rows=decoder_trials.library_imports(Path('/tmp'))
        self.assertEqual(rows[0]['kind'],'private_decoder_import')
        self.assertEqual(rows[0]['status'],'private_import')
        self.assertEqual(rows[0]['missing_files'],[])
        self.assertTrue(rows[1]['missing_files'])
        self.assertIsInstance(rows[0]['created_at'],float)
        self.assertEqual(rows[0]['evaluation_status'],'not_re_evaluated_dataset_excluded')

    def test_models_api_keeps_existing_models_and_adds_separate_private_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            handler=Mock(path='/models')
            job={'id':'a'*32,'prompt':'Classifier fixture','project_id':'p','recipe':'classifier','status':'passed'}
            private=[{'id':'b'*32,'kind':'private_decoder_import','status':'private_import'}]
            with patch.object(studio,'ROOT',Path(temporary)), patch.object(studio,'JOBS',{job['id']:job}), \
                 patch.object(studio.chat_history,'list_projects',return_value=[{'id':'p','name':'Existing project'}]), \
                 patch.object(studio,'missing_model_files',return_value=[]), patch.object(decoder_trials,'library_imports',return_value=private):
                studio.Handler.do_GET(handler)
            response=handler.respond.call_args.args[0]
            self.assertEqual(response['models'][0]['recipe'],'classifier')
            self.assertEqual(response['models'][0]['status'],'passed')
            self.assertEqual(response['private_imports'],private)
            self.assertEqual(job['status'],'passed')
