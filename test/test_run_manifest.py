import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import recipe_contracts, run_manifest, studio


class RunManifestTest(unittest.TestCase):
    def fixture(self, folder):
        rows = [{'text': 'private local example', 'label': 'a', 'group': 'one', 'split': 'train'},
                {'text': 'held out', 'label': 'a', 'group': 'two', 'split': 'test'}]
        job = {'id': 'd' * 32, 'recipe': 'classifier', 'target': .8, 'idle': False,
               'recipe_contract': recipe_contracts.recipe_contract('classifier')}
        model = folder / 'candidate.joblib'
        model.write_bytes(b'fixture model; no deserialization needed')
        (folder / 'dataset.json').write_text(json.dumps(rows))
        manifest = run_manifest.build(job, rows, {'passed': True, 'split_seed': 3}, model,
                                      recipe_contracts.export_metadata(job))
        run_manifest.write(folder, manifest)
        return rows, job, manifest

    def test_manifest_binds_inputs_splits_runtime_and_candidate_without_raw_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            rows, job, manifest = self.fixture(folder)
            self.assertEqual(run_manifest.read(folder), manifest)
            self.assertEqual(manifest['randomness']['split_seed'], 3)
            self.assertEqual(manifest['dataset']['sha256'], run_manifest.digest(rows))
            self.assertEqual(set(manifest['partitions']), {'train', 'test'})
            self.assertIn('numpy', manifest['runtime']['dependencies'])
            self.assertIn('studio.py', manifest['components'])
            self.assertNotIn('private local example', json.dumps(manifest))
            self.assertEqual(manifest['settings_sha256'], run_manifest.digest(recipe_contracts.export_metadata(job)))
            rows[0]['split'] = 'test'
            self.assertNotEqual(manifest['dataset']['sha256'], run_manifest.digest(rows))

    def test_tampered_model_dataset_and_metadata_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for part in ('model', 'dataset', 'metadata', 'path', 'version'):
                rows, _, manifest = self.fixture(folder)
                if part == 'model':
                    (folder / 'candidate.joblib').write_bytes(b'changed')
                elif part == 'dataset':
                    (folder / 'dataset.json').write_text('[]')
                elif part == 'metadata':
                    manifest['recipe']['parameters']['target'] = .9
                    run_manifest.write(folder, manifest)
                elif part == 'path':
                    manifest['artifact']['name'] = '../candidate.joblib'
                    run_manifest.write(folder, manifest)
                else:
                    manifest['schema_version'] = True
                    run_manifest.write(folder, manifest)
                with self.subTest(part=part), self.assertRaises(ValueError):
                    run_manifest.read(folder)

    def test_read_route_after_restart_and_legacy_failure_do_not_write_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'training-sessions' / ('d' * 32)
            folder.mkdir(parents=True)
            _, job, manifest = self.fixture(folder)
            job['status'] = 'preview_ready'
            # Reload only persisted job state; no in-memory candidate is required.
            restored = json.loads(json.dumps(job))
            handler = Mock(path='/jobs/' + job['id'] + '/manifest')
            handler.authorized.return_value = True
            with patch.object(studio, 'ROOT', root), patch.object(studio, 'JOBS', {job['id']: restored}), patch.object(studio, 'store_job') as store:
                studio.Handler.do_GET(handler)
                self.assertEqual(handler.respond.call_args.args[0], manifest)
                (folder / 'run-manifest.json').unlink()
                studio.Handler.do_GET(handler)
                self.assertEqual(handler.respond.call_args.args[1], 409)
                store.assert_not_called()
            self.assertEqual(restored, job)

    def test_release_keeps_training_runtime_and_rebinds_exported_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'training-sessions' / ('d' * 32)
            folder.mkdir(parents=True)
            rows, job, manifest = self.fixture(folder)
            manifest['runtime']['python'] = 'recorded-training-runtime'
            run_manifest.write(folder, manifest)
            job['status'] = 'exporting'
            with patch.object(studio, 'ROOT', root), patch.object(studio, 'activity'), patch.object(studio, 'store_job'), patch.object(studio, 'CANDIDATES', {}):
                studio.export_candidate(job, ({'fixture': 'model'}, rows, manifest['evaluation']))
            self.assertEqual(job['status'], 'passed')
            released = run_manifest.read(root / job['id'])
            self.assertEqual(released['runtime']['python'], 'recorded-training-runtime')
            self.assertEqual(released['artifact']['name'], 'model.joblib')
            self.assertEqual(released['dataset'], manifest['dataset'])

    def test_approval_revision_binds_settings_dataset_and_goal_and_renewal_has_new_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            rows, job, _ = self.fixture(Path(temporary))
            metadata = recipe_contracts.export_metadata(job)
            receipt = run_manifest.approve(job, rows, metadata)
            job['training_approval'] = receipt
            run_manifest.validate_approval(job, rows, metadata)
            renewed = run_manifest.approve(job, rows, metadata)
            self.assertEqual(renewed['revision'], receipt['revision'])
            self.assertNotEqual(renewed['approval_id'], receipt['approval_id'])
            for change in ('rows', 'target', 'goal', 'receipt'):
                from copy import deepcopy
                altered_job, altered_rows = deepcopy(job), deepcopy(rows)
                if change == 'rows': altered_rows[0]['text'] = 'changed input'
                if change == 'target': altered_job['target'] = .9
                if change == 'goal': altered_job['prompt'] = 'changed goal'
                if change == 'receipt': altered_job['training_approval']['revision'] = 'tampered'
                with self.subTest(change=change), self.assertRaises(run_manifest.ApprovalChanged):
                    run_manifest.validate_approval(altered_job, altered_rows, recipe_contracts.export_metadata(altered_job))
            # Receipts survive a JSON roundtrip; old jobs remain readable without writes.
            restored = json.loads(json.dumps(job))
            run_manifest.validate_approval(restored, rows, metadata)
            del restored['training_approval']
            run_manifest.validate_approval(restored, rows, metadata)
            self.assertNotIn('training_approval', restored)

    def test_changed_queued_inputs_return_to_approval_without_invoking_trainer(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            rows, job, _ = self.fixture(folder)
            job.update(status='queued', idle=False)
            job['training_approval'] = run_manifest.approve(job, rows, recipe_contracts.export_metadata(job))
            rows[0]['text'] = 'changed after approval'
            with patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'TRAINING_WORKERS', {job['id']}), patch.object(studio, 'store_job'), patch.object(studio, 'check_training_power'), patch.object(recipe_contracts, 'execute') as execute:
                studio.run(job)
                execute.assert_not_called()
                self.assertEqual(job['status'], 'dataset_ready')
                self.assertIn('approve training again', job['error'])
                self.assertEqual(studio.TRAINING_DATA[job['id']], rows)
