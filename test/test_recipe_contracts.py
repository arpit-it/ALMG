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
                patch.object(studio, 'TRAINING_DATA', {job['id']: ([{'text': 'example', 'label': 'a', 'group': 'g'}] if job['recipe'] == 'classifier' else studio.image_recipe.dataset())}), \
                patch.object(studio, 'CANDIDATES', {}), patch.object(studio, 'store_job'), \
                patch.object(studio, 'train', return_value=(object(), [{'text': 'example', 'label': 'a', 'group': 'g'}], {'passed': True})):
            studio.run(job)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('validation_macro_f1', job['error'])
            self.assertNotIn(job['id'], studio.CANDIDATES)
            self.assertEqual(list(Path(folder).rglob('candidate.*')), [])

    def test_candidate_models_match_existing_runtime_and_export_formats(self):
        from sklearn.pipeline import Pipeline
        from sklearn.dummy import DummyClassifier
        recipe_contracts.validate_model('classifier', 'local', Pipeline([('classifier', DummyClassifier())]))
        with self.assertRaises(ValueError):
            recipe_contracts.validate_model('classifier', 'local', {'format': 'almg-shapes-v1'})
        for mode, expected in [('local', 'almg-shapes-v1'), ('web_images', 'almg-caption-ridge-v1')]:
            if mode == 'web_images':
                recipe_contracts.validate_model('text_to_image', mode, {'format': expected, 'size': 48, 'vocabulary': [], 'weights': [[0.] * (48 * 48 * 3)]})
            else:
                model, _, _ = studio.image_recipe.train(studio.image_recipe.dataset(), 0.8, lambda message: None)
                recipe_contracts.validate_model('text_to_image', mode, model)
            for model in ({'format': 'unknown', 'size': 48}, {'format': expected, 'size': True},
                          {'format': expected, 'size': 64}, {'format': expected, 'size': 48, 'weights': [float('nan')]},
                          {'format': expected, 'size': 48, 'weights': object()}):
                with self.subTest(mode=mode, model=model), self.assertRaises(ValueError):
                    recipe_contracts.validate_model('text_to_image', mode, model)

    def test_invalid_model_never_saves_preview_candidate(self):
        import tempfile
        from pathlib import Path
        job = {'id': 'invalid-model', 'status': 'queued', 'idle': False,
               'recipe': 'text_to_image', 'target': 0.8}
        metrics = {'held_out_pixel_accuracy': 0.9, 'target_pixel_accuracy': 0.8, 'passed': True}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), \
                patch.object(studio, 'TRAINING_DATA', {job['id']: ([{'text': 'example', 'label': 'a', 'group': 'g'}] if job['recipe'] == 'classifier' else studio.image_recipe.dataset())}), \
                patch.object(studio, 'CANDIDATES', {}), patch.object(studio, 'store_job'), \
                patch.object(studio.image_recipe, 'train', return_value=({'format': 'unknown'}, studio.image_recipe.dataset(), metrics)):
            studio.run(job)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('unsupported model format', job['error'])
            self.assertNotIn(job['id'], studio.CANDIDATES)
            self.assertEqual(list(Path(folder).rglob('candidate.*')), [])

    def test_image_payloads_require_complete_inference_dimensions(self):
        from copy import deepcopy
        model, _, _ = studio.image_recipe.train(studio.image_recipe.dataset(), 0.8, lambda message: None)
        invalid = []
        for key in ('masks', 'palette', 'background'):
            candidate = deepcopy(model)
            candidate.pop(key)
            invalid.append(candidate)
        candidate = deepcopy(model)
        candidate['masks']['circle:center'] = [0.5]
        invalid.append(candidate)
        candidate = deepcopy(model)
        candidate['palette']['red'] = [256, 0, 0]
        invalid.append(candidate)
        candidate = deepcopy(model)
        candidate['masks']['circle:center'][0] = '0.5'
        invalid.append(candidate)
        for candidate in invalid:
            with self.assertRaisesRegex(ValueError, 'invalid masks'):
                recipe_contracts.validate_model('text_to_image', 'local', candidate)
        for vocabulary, weights in [(['red'], [[0.] * 6912]), (['red', 'red'], [[0.] * 6912] * 3),
                                    ([3], [[0.] * 6912] * 2), ([], [['0'] * 6912])]:
            with self.assertRaisesRegex(ValueError, 'invalid vocabulary'):
                recipe_contracts.validate_model('text_to_image', 'web_images',
                    {'format': 'almg-caption-ridge-v1', 'size': 48, 'vocabulary': vocabulary, 'weights': weights})

    def test_release_contract_preserves_snapshot_and_labels_legacy_fallback(self):
        from copy import deepcopy
        snapshot = recipe_contracts.recipe_contract('classifier')
        snapshot['description'] = 'Description at approval time'
        job = {'recipe': 'classifier', 'recipe_contract': snapshot, 'target': 0.9,
               'idle': False, 'allow_repair': True}
        before = deepcopy(job)
        metadata = recipe_contracts.export_metadata(job)
        self.assertEqual(metadata['origin'], 'approved_job_snapshot')
        self.assertEqual(metadata['contract'], snapshot)
        self.assertEqual(metadata['parameters'], {'target': 0.9, 'idle': False, 'allow_repair': True})
        metadata['contract']['description'] = 'changed copy'
        self.assertEqual(job, before)
        legacy = {'recipe': 'text_to_image', 'target': 0.8, 'allow_repair': False}
        fallback = recipe_contracts.export_metadata(legacy)
        self.assertEqual(fallback['origin'], 'legacy_catalog_fallback')
        self.assertEqual(fallback['contract']['id'], 'text_to_image')
        self.assertEqual(fallback['parameters'], {'target': 0.8})
        self.assertNotIn('recipe_contract', legacy)

    def test_release_bundle_contains_recipe_contract_alongside_model_and_metrics(self):
        import tempfile
        from pathlib import Path
        for legacy in (False, True):
            job = {'id': 'release-contract', 'recipe': 'text_to_image', 'status': 'exporting',
                   'target': 0.8, 'idle': False}
            if not legacy:
                job['recipe_contract'] = recipe_contracts.recipe_contract('text_to_image')
            with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), \
                    patch.object(studio, 'store_job'), patch.object(studio, 'activity'), patch.object(studio, 'CANDIDATES', {}):
                studio.export_candidate(job, ({'format': 'almg-shapes-v1'}, [], {'passed': True}))
                out = Path(folder) / job['id']
                self.assertEqual(job['status'], 'passed')
                self.assertTrue(all((out / name).is_file() for name in ['model.json', 'dataset.jsonl', 'report.json', 'recipe-contract.json']))
                metadata = json.loads((out / 'recipe-contract.json').read_text())
                self.assertEqual(metadata['origin'], 'legacy_catalog_fallback' if legacy else 'approved_job_snapshot')
                self.assertEqual(metadata['parameters'], {'target': 0.8, 'idle': False})

    def test_dataset_contract_rejects_invalid_rows_and_missing_image_splits(self):
        recipe_contracts.validate_dataset('classifier', 'local', [{'text': 'fruit', 'label': 'fruit', 'group': 'one'}], ['fruit'])
        for rows in ([], {}, [None], [{'text': ' ', 'label': 'fruit', 'group': 'one'}],
                     [{'text': 'fruit', 'label': 'unknown', 'group': 'one'}],
                     [{'text': 'fruit', 'label': 'fruit', 'group': ''}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                recipe_contracts.validate_dataset('classifier', 'local', rows, ['fruit'])
        rows = studio.image_recipe.dataset()
        recipe_contracts.validate_dataset('text_to_image', 'local', rows)
        with self.assertRaisesRegex(ValueError, 'both training and held-out'):
            recipe_contracts.validate_dataset('text_to_image', 'local', [row for row in rows if row['split'] == 'train'])
        with self.assertRaisesRegex(ValueError, 'encoded image'):
            recipe_contracts.validate_dataset('text_to_image', 'web_images', [{'text': 'caption', 'split': 'train'}])

    def test_invalid_dataset_does_not_invoke_trainer_and_retains_rows(self):
        job = {'id': 'invalid-dataset', 'status': 'queued', 'idle': False, 'recipe': 'classifier', 'target': 0.8, 'plan': {'labels': ['a']}}
        rows = [{'text': 'example', 'label': 'a'}]
        with patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'store_job'), patch.object(studio, 'train') as trainer:
            studio.run(job)
            trainer.assert_not_called()
            self.assertEqual(job['status'], 'failed')
            self.assertIn('nonempty group', job['error'])
            self.assertEqual(studio.TRAINING_DATA[job['id']], rows)

    def test_execution_variants_reject_recipe_source_mismatches(self):
        for mode in (None, 'local', 'synthetic', 'local_csv', 'web'):
            self.assertEqual(recipe_contracts.execution_variant('classifier', mode), 'classifier')
        for mode in (None, 'local', 'synthetic'):
            self.assertEqual(recipe_contracts.execution_variant('text_to_image', mode), 'local shapes')
        self.assertEqual(recipe_contracts.execution_variant('text_to_image', 'web_images'), 'Commons captions')
        for recipe, mode in [('classifier', 'web_images'), ('text_to_image', 'web'), ('text_to_image', 'local_csv'), ('classifier', 'unknown')]:
            with self.subTest(recipe=recipe, mode=mode), self.assertRaisesRegex(ValueError, 'not supported'):
                recipe_contracts.execution_variant(recipe, mode)

    def test_invalid_execution_mode_leaves_approval_pending_without_worker(self):
        import io
        from unittest.mock import Mock
        job = {'id': 'mode-fixture', 'recipe': 'text_to_image', 'mode': 'local_csv', 'status': 'dataset_ready'}
        body = json.dumps({'target': 0.8, 'idle': False}).encode()
        handler = Mock(path='/jobs/mode-fixture/start', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        with patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'store_job'), patch.object(studio.threading, 'Thread') as worker:
            studio.Handler.do_POST(handler)
        self.assertEqual(job['status'], 'dataset_ready')
        self.assertEqual(handler.respond.call_args.args[1], 400)
        worker.assert_not_called()

    def test_execution_modes_are_derived_from_versioned_catalog(self):
        for contract in recipe_contracts.recipe_catalog():
            modes = contract['dataset']['modes']
            self.assertTrue(modes)
            for mode, details in modes.items():
                self.assertTrue(details['label'])
                self.assertIn(details['variant'], contract['metrics'])
                self.assertEqual(recipe_contracts.execution_variant(contract['id'], mode), details['variant'])
        with patch.dict(recipe_contracts._CONTRACTS['classifier']['dataset']['modes'],
                        {'fixture_mode': {'label': 'Fixture', 'variant': 'classifier'}}):
            self.assertEqual(recipe_contracts.execution_variant('classifier', 'fixture_mode'), 'classifier')

    def test_image_dataset_validates_numeric_values_and_training_coverage(self):
        from copy import deepcopy
        rows = studio.image_recipe.dataset()
        for field, value in [('mask', float('nan')), ('mask', '1'), ('mask', 2),
                             ('rgb', 256), ('rgb', -1), ('rgb', True)]:
            invalid = deepcopy(rows)
            invalid[0][field][0] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'mask values'):
                recipe_contracts.validate_dataset('text_to_image', 'synthetic', invalid)
        invalid = [row for row in rows if not (row['shape'] == 'circle' and row['position'] == 'center' and row['split'] == 'train')]
        with self.assertRaisesRegex(ValueError, 'every shape/position'):
            recipe_contracts.validate_dataset('text_to_image', 'synthetic', invalid)

    def test_caption_dataset_requires_prepared_rgb_png(self):
        import base64
        import io
        from PIL import Image
        def encoded(size, mode, format):
            output = io.BytesIO()
            Image.new(mode, size).save(output, format=format)
            return base64.b64encode(output.getvalue()).decode()
        valid = encoded((48, 48), 'RGB', 'PNG')
        rows = [{'text': 'local fixture', 'split': split, 'image': valid} for split in ('train', 'test')]
        recipe_contracts.validate_dataset('text_to_image', 'web_images', rows)
        for content in ('invalid base64', base64.b64encode(b'not an image').decode(),
                        encoded((49, 48), 'RGB', 'PNG'), encoded((48, 48), 'L', 'PNG'),
                        encoded((48, 48), 'RGB', 'JPEG'), 'A' * 100001):
            with self.assertRaisesRegex(ValueError, 'valid prepared'):
                recipe_contracts.validate_dataset('text_to_image', 'web_images', [{**rows[0], 'image': content}, rows[1]])

    def test_execution_interface_passes_classifier_callbacks_and_checks_outputs(self):
        from unittest.mock import Mock
        from sklearn.pipeline import Pipeline
        from sklearn.dummy import DummyClassifier
        rows = [{'text': 'fruit', 'label': 'fruit', 'group': 'one'}]
        model = Pipeline([('classifier', DummyClassifier())])
        metrics = {'validation_macro_f1': 0.9, 'test_macro_f1': 0.9, 'target_macro_f1': 0.8, 'passed': True}
        trainer = Mock(return_value=(model, rows, metrics))
        report, repair = Mock(), Mock()
        result = recipe_contracts.execute('classifier', 'synthetic', rows,
            {'target': 0.8, 'allow_repair': True}, trainers={'classifier': trainer}, labels=['fruit'],
            report=report, repair=repair, checkpoint_path='fixture-checkpoint')
        self.assertEqual(result, (model, rows, metrics))
        trainer.assert_called_once_with(rows, ['fruit'], 0.8, report=report, repair=repair, checkpoint_path='fixture-checkpoint')
        for output in (None, (model, rows), (model, [], metrics), (model, rows, {'passed': True})):
            trainer.return_value = output
            with self.assertRaises(ValueError):
                recipe_contracts.execute('classifier', 'synthetic', rows, {'target': 0.8},
                    trainers={'classifier': trainer}, labels=['fruit'], report=report)

    def test_execution_interface_runs_real_shape_recipe_and_requires_adapter(self):
        rows = studio.image_recipe.dataset()
        model, evaluated, metrics = recipe_contracts.execute('text_to_image', 'synthetic', rows,
            {'target': 0.8}, trainers={'local shapes': studio.image_recipe.train}, report=lambda message: None)
        self.assertEqual(model['format'], 'almg-shapes-v1')
        self.assertEqual(evaluated, rows)
        self.assertTrue(metrics['passed'])
        with self.assertRaisesRegex(ValueError, 'No local trainer'):
            recipe_contracts.execute('text_to_image', 'synthetic', rows, {'target': 0.8}, trainers={}, report=lambda message: None)
