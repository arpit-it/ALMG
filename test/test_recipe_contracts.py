import json
import unittest
from unittest.mock import patch
from backend import recipe_contracts, studio


class RecipeContractsTest(unittest.TestCase):
    def test_catalog_describes_only_existing_recipes_and_all_contract_sections(self):
        catalog = recipe_contracts.recipe_catalog()
        self.assertEqual({item['id'] for item in catalog}, {'classifier', 'text_to_image'})
        self.assertEqual(set(studio.TRAINING_RECIPES), {'classifier', 'text_to_image'})
        for item in catalog:
            self.assertEqual(item['schema_version'], 1)
            self.assertEqual(item['version'], 1)
            self.assertTrue(all(item[key] for key in ['dataset', 'hardware', 'parameters', 'metrics', 'exports', 'resume']))
            self.assertEqual(json.loads(json.dumps(item)), item)
        self.assertIn('test_macro_f1', catalog[0]['metrics']['classifier'])
        self.assertIn('held_out_pixel_similarity', catalog[1]['metrics']['Commons captions'])

    def test_snapshots_are_independent_and_unknown_recipes_are_rejected(self):
        snapshot = recipe_contracts.recipe_contract('classifier')
        snapshot['parameters'][0]['default'] = 99
        self.assertEqual(recipe_contracts.recipe_contract('classifier')['parameters'][0]['default'], 0.8)
        for value in ('lora', None, []):
            with self.assertRaises(ValueError): recipe_contracts.recipe_contract(value)

    def test_planning_records_selected_contract_with_saved_job(self):
        job = {'id': 'contract-fixture', 'recipe': 'classifier', 'prompt': 'Classify fruit and stars'}
        with patch.object(studio, 'plan', return_value={'labels': ['fruit', 'stars'], 'queries': ['fruit', 'stars']}), patch.object(studio, 'store_job') as saved:
            studio.Handler.make_plan(job)
        self.assertEqual(job['status'], 'approval')
        self.assertEqual(job['recipe_contract'], recipe_contracts.recipe_contract('classifier'))
        self.assertTrue(saved.called)

    def test_catalog_and_recipe_read_routes_expose_versioned_contracts(self):
        from unittest.mock import Mock
        for path in ('/recipes', '/recipes/classifier', '/recipes/unknown'):
            handler = Mock(path=path)
            handler.authorized.return_value = True
            studio.Handler.do_GET(handler)
            response = handler.respond.call_args
            if path == '/recipes':
                self.assertEqual(response.args[0]['schema_version'], 1)
                self.assertEqual(len(response.args[0]['recipes']), 2)
            elif path.endswith('classifier'):
                self.assertEqual(response.args[0], recipe_contracts.recipe_contract('classifier'))
            else:
                self.assertEqual(response.args[1], 404)

    def test_legacy_approval_job_survives_restart_without_rewrite(self):
        import tempfile
        from pathlib import Path
        job_id = 'e' * 32
        legacy = {'id': job_id, 'recipe': 'classifier', 'status': 'approval',
                  'prompt': 'Legacy fixture', 'plan': {'labels': ['fruit', 'stars'], 'queries': ['fruit', 'stars']}}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'JOBS', {}):
            directory = Path(folder) / 'training-sessions'
            directory.mkdir()
            record = directory / (job_id + '.json')
            record.write_text(json.dumps(legacy))
            before = record.read_bytes()
            studio.restore_jobs()
            self.assertEqual(studio.JOBS[job_id], legacy)
            self.assertEqual(record.read_bytes(), before)
            self.assertNotIn('recipe_contract', studio.JOBS[job_id])
