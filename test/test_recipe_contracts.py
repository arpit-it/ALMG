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

    def test_execution_parameters_enforce_types_bounds_and_recipe_options(self):
        valid = recipe_contracts.training_parameters('classifier', {'target': 0.9, 'idle': False, 'allow_repair': True})
        self.assertEqual(valid, {'target': 0.9, 'idle': False, 'allow_repair': True})
        self.assertTrue(recipe_contracts.training_parameters('classifier', {'target': 1})['idle'])
        for target in (True, '0.8', float('nan'), float('inf'), 10 ** 1000, 0, -1, 1.1):
            with self.assertRaises(ValueError): recipe_contracts.training_parameters('classifier', {'target': target})
        for values in ({'target': 0.8, 'idle': 'false'}, {'target': 0.8, 'allow_repair': 1},
                       {'target': 0.8, 'unknown': True}, {}):
            with self.assertRaises(ValueError): recipe_contracts.training_parameters('classifier', values)
        self.assertFalse(recipe_contracts.training_parameters('text_to_image', {'target': 0.8, 'allow_repair': False})['allow_repair'])
        with self.assertRaises(ValueError):
            recipe_contracts.training_parameters('text_to_image', {'target': 0.8, 'allow_repair': True})

    def test_unsupported_snapshot_rejects_execution_and_legacy_jobs_use_catalog(self):
        snapshot = recipe_contracts.recipe_contract('classifier')
        snapshot['version'] = 99
        with self.assertRaisesRegex(ValueError, 'unsupported recipe contract'):
            recipe_contracts.training_parameters('classifier', {'target': 0.8}, snapshot)
        self.assertEqual(recipe_contracts.training_parameters('classifier', {'target': 0.8})['target'], 0.8)

    def test_invalid_parameters_leave_image_approval_pending_without_worker(self):
        import io
        from unittest.mock import Mock
        job = {'id': 'parameter-fixture', 'recipe': 'text_to_image', 'status': 'dataset_ready'}
        body = json.dumps({'target': 0.8, 'idle': 'false'}).encode()
        handler = Mock(path='/jobs/parameter-fixture/start', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        with patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'store_job'), patch.object(studio.threading, 'Thread') as worker:
            studio.Handler.do_POST(handler)
        self.assertEqual(job['status'], 'dataset_ready')
        self.assertEqual(handler.respond.call_args.args[1], 400)
        worker.assert_not_called()

    def test_evaluation_metrics_enforce_required_scores_and_approved_target(self):
        valid = {'validation_macro_f1': 0.9, 'test_macro_f1': 0.85,
                 'target_macro_f1': 0.8, 'passed': True}
        recipe_contracts.validate_metrics('classifier', 'local', valid, 0.8)
        for changes in ({'test_macro_f1': None}, {'test_macro_f1': True},
                        {'test_macro_f1': float('nan')}, {'test_macro_f1': float('inf')},
                        {'test_macro_f1': 1.1}, {'test_macro_f1': 0.7},
                        {'target_macro_f1': 0.9}, {'passed': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                recipe_contracts.validate_metrics('classifier', 'local', {**valid, **changes}, 0.8)
        recipe_contracts.validate_metrics('classifier', 'local', {**valid, 'passed': False}, 0.8)
        for mode, key in [('local', 'held_out_pixel_accuracy'), ('web_images', 'held_out_pixel_similarity')]:
            recipe_contracts.validate_metrics('text_to_image', mode,
                {key: 0.9, 'target_pixel_accuracy': 0.8, 'passed': True}, 0.8)

    def test_invalid_evaluation_never_saves_preview_candidate(self):
        import tempfile
        from pathlib import Path
        job = {'id': 'invalid-result', 'status': 'queued', 'idle': False,
               'recipe': 'classifier', 'target': 0.8, 'plan': {'labels': ['a', 'b']}}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), \
                patch.object(studio, 'TRAINING_DATA', {job['id']: []}), \
                patch.object(studio, 'CANDIDATES', {}), patch.object(studio, 'store_job'), \
                patch.object(studio, 'train', return_value=(object(), [], {'passed': True})):
            studio.run(job)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('validation_macro_f1', job['error'])
            self.assertNotIn(job['id'], studio.CANDIDATES)
            self.assertEqual(list(Path(folder).rglob('candidate.*')), [])
