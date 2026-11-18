import unittest
from unittest.mock import patch
from backend import studio


class TrainingWindowTest(unittest.TestCase):
    def test_busy_device_waits_then_resumes_at_same_boundary(self):
        job = {'id': 'window-fixture', 'status': 'training', 'idle': True}
        rows = [{'text': 'fixture'}]
        with patch.object(studio, 'idle_ready', side_effect=[False, False, True]), patch.object(studio.time, 'sleep') as sleep, patch.object(studio, 'store_job'), patch.object(studio, 'activity') as activity, patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio.training_resources, 'check', return_value={'fixture': True}) as check:
            studio.wait_for_training_window(job)
        self.assertEqual(job['status'], 'training')
        self.assertEqual(sleep.call_count, 2)
        check.assert_called_once_with(rows, studio.ROOT)
        self.assertIn('paused between steps', activity.call_args_list[0].args[1])
        self.assertIn('Resuming training', activity.call_args_list[1].args[1])

    def test_cancelled_wait_never_resumes_or_runs_resource_probe(self):
        job = {'id': 'cancel-fixture', 'status': 'training', 'idle': True}
        def cancel(_): job['status'] = 'cancelled'
        with patch.object(studio, 'idle_ready', return_value=False), patch.object(studio.time, 'sleep', side_effect=cancel), patch.object(studio, 'store_job'), patch.object(studio, 'activity'), patch.object(studio.training_resources, 'check') as check:
            with self.assertRaises(studio.TrainingCancelled): studio.wait_for_training_window(job)
        self.assertEqual(job['status'], 'cancelled')
        check.assert_not_called()

    def test_immediate_training_does_not_probe_idle_or_power(self):
        with patch.object(studio, 'idle_ready') as probe:
            studio.wait_for_training_window({'idle': False})
        probe.assert_not_called()

    def test_macos_idle_and_power_gate_and_probe_failure(self):
        from unittest.mock import Mock
        import subprocess
        query = Mock(return_value=600.0)
        core_graphics = Mock(CGEventSourceSecondsSinceLastEventType=query)
        with patch.object(studio.sys, 'platform', 'darwin'), patch.object(studio.ctypes, 'CDLL', return_value=core_graphics), patch.object(studio.subprocess, 'check_output', return_value="Now drawing from 'AC Power'") as power:
            self.assertTrue(studio.idle_ready())
            query.return_value = 599.9
            self.assertFalse(studio.idle_ready())
            query.return_value = 900.0
            power.return_value = "Now drawing from 'Battery Power'"
            self.assertFalse(studio.idle_ready())
            power.side_effect = subprocess.TimeoutExpired('pmset', 3)
            self.assertFalse(studio.idle_ready())

    def test_clock_guard_distinguishes_elapsed_work_from_suspended_uptime(self):
        self.assertEqual(studio.check_training_clock((100, 10), (200, 110)), (200, 110))
        self.assertEqual(studio.check_training_clock((100, 10), (101, 11)), (101, 11))
        with self.assertRaisesRegex(studio.TrainingWindowInterrupted, 'approve training again'):
            studio.check_training_clock((100, 10), (160, 11))

    def test_clock_interruption_retains_dataset_and_returns_to_approval(self):
        job = {'id': 'sleep-fixture', 'status': 'queued', 'idle': False,
               'recipe': 'text_to_image', 'target': 0.8}
        rows = studio.image_recipe.dataset()
        with patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'store_job'), patch.object(studio, 'training_clock', side_effect=[(100, 10), (160, 11)]), patch.object(studio.training_resources, 'check', return_value={}), patch.object(studio.image_recipe, 'train') as trainer:
            trainer.side_effect = lambda rows, target, report: report('Before fitting')
            studio.run(job)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertIn('Sleep or a system-clock change', job['error'])
            self.assertEqual(studio.TRAINING_DATA[job['id']], rows)
            self.assertNotIn(job['id'], studio.TRAINING_WORKERS)

    def test_readiness_reports_idle_power_and_unavailable_states(self):
        from unittest.mock import Mock
        import subprocess
        query = Mock(return_value=42.9)
        with patch.object(studio.sys, 'platform', 'darwin'), patch.object(studio.ctypes, 'CDLL', return_value=Mock(CGEventSourceSecondsSinceLastEventType=query)), patch.object(studio.subprocess, 'check_output', return_value="Now drawing from 'AC Power'") as power:
            state = studio.training_readiness()
            self.assertFalse(state['ready'])
            self.assertTrue(state['ac_power'])
            self.assertEqual(state['idle_seconds'], 42)
            self.assertIn('42 of 600', state['message'])
            query.return_value = 700.
            self.assertTrue(studio.training_readiness()['ready'])
            power.return_value = "Now drawing from 'Battery Power'"
            self.assertFalse(studio.training_readiness()['ac_power'])
            power.side_effect = subprocess.TimeoutExpired('pmset', 3)
            self.assertIsNone(studio.training_readiness()['idle_seconds'])

    def test_waiting_job_readiness_is_fresh_response_metadata_not_saved_state(self):
        from unittest.mock import Mock
        job = {'id': 'readiness-fixture', 'status': 'waiting_idle'}
        handler = Mock(path='/jobs/readiness-fixture')
        state = {'ready': False, 'message': 'Fixture waiting'}
        with patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'training_readiness', return_value=state):
            studio.Handler.do_GET(handler)
        self.assertEqual(handler.respond.call_args.args[0]['training_readiness'], state)
        self.assertNotIn('training_readiness', job)

    def test_readiness_route_exposes_current_probe_without_job(self):
        from unittest.mock import Mock
        handler = Mock(path='/runtime/training-readiness')
        state = {'ready': True, 'ac_power': True, 'idle_seconds': 700, 'message': 'Ready fixture'}
        with patch.object(studio, 'training_readiness', return_value=state):
            studio.Handler.do_GET(handler)
        self.assertEqual(handler.respond.call_args.args[0], state)

    def test_interrupted_image_training_restores_valid_saved_rows_for_reapproval(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest.mock import Mock
        for status in ('training', 'waiting_idle'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                job_id = 'c' * 32
                directory = root / 'training-sessions' / job_id
                directory.mkdir(parents=True)
                data = directory / 'dataset.json'
                data.write_text(json.dumps(studio.image_recipe.dataset()))
                before = data.read_bytes()
                record = directory.parent / (job_id + '.json')
                record.write_text(json.dumps({'id': job_id, 'recipe': 'text_to_image', 'mode': 'synthetic', 'status': status}))
                with patch.object(studio, 'ROOT', root), patch.object(studio, 'JOBS', {}), patch.object(studio, 'TRAINING_DATA', {}), patch.object(studio.threading, 'Thread') as worker:
                    studio.restore_jobs()
                    job = studio.JOBS[job_id]
                    self.assertEqual(job['status'], 'dataset_ready')
                    self.assertIn('image fitting restarts', job['error'])
                    self.assertEqual(len(studio.TRAINING_DATA[job_id]), 45)
                    self.assertEqual(json.loads(record.read_text())['status'], 'dataset_ready')
                    self.assertEqual(data.read_bytes(), before)
                    worker.assert_not_called()

    def test_corrupt_interrupted_image_dataset_is_not_reopened(self):
        import tempfile
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = 'd' * 32
            directory = root / 'training-sessions' / job_id
            directory.mkdir(parents=True)
            (directory / 'dataset.json').write_text('[{"text":"bad"}]')
            (directory.parent / (job_id + '.json')).write_text(json.dumps({'id': job_id, 'recipe': 'text_to_image', 'status': 'training'}))
            with patch.object(studio, 'ROOT', root), patch.object(studio, 'JOBS', {}), patch.object(studio, 'TRAINING_DATA', {}):
                studio.restore_jobs()
                self.assertEqual(studio.JOBS[job_id]['status'], 'failed')
                self.assertNotIn(job_id, studio.TRAINING_DATA)

    def test_cancelled_image_reopen_requires_confirmation_stopped_worker_and_valid_rows(self):
        import tempfile
        import json
        from pathlib import Path
        job = {'id': 'e' * 32, 'recipe': 'text_to_image', 'mode': 'synthetic', 'status': 'cancelled'}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'TRAINING_WORKERS', set()):
            directory = Path(folder) / 'training-sessions' / job['id']
            directory.mkdir(parents=True)
            data = directory / 'dataset.json'
            rows = studio.image_recipe.dataset()
            data.write_text(json.dumps(rows))
            before = data.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Confirm reopening'):
                studio.cancelled_training_rows(job, False)
            studio.TRAINING_WORKERS.add(job['id'])
            with self.assertRaisesRegex(ValueError, 'still stopping'):
                studio.cancelled_training_rows(job, True)
            studio.TRAINING_WORKERS.clear()
            self.assertEqual(studio.cancelled_training_rows(job, True), rows)
            self.assertEqual(data.read_bytes(), before)
            data.write_text('[{"text":"invalid"}]')
            with self.assertRaisesRegex(ValueError, 'saved dataset is invalid'):
                studio.cancelled_training_rows(job, True)

    def test_cancelled_image_reopen_route_prepares_without_starting_training(self):
        import io
        import json
        from unittest.mock import Mock
        job = {'id': 'image-cancel-fixture', 'recipe': 'text_to_image', 'status': 'cancelled'}
        body = json.dumps({'confirmed': True}).encode()
        handler = Mock(path='/jobs/image-cancel-fixture/reopen-cancelled', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        rows = studio.image_recipe.dataset()
        with patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'store_job'), patch.object(studio, 'cancelled_training_rows', return_value=rows), patch.object(studio.threading, 'Thread') as thread:
            studio.Handler.do_POST(handler)
        self.assertEqual(job['status'], 'creating_dataset')
        self.assertEqual(thread.call_args.kwargs['target'], studio.prepare_dataset)
        self.assertEqual(thread.call_args.kwargs['args'], (job, rows))

    def test_native_power_event_invalidates_only_active_jobs(self):
        active = {'id': 'active-power', 'status': 'training'}
        ready = {'id': 'ready-power', 'status': 'dataset_ready'}
        with patch.object(studio, 'JOBS', {job['id']: job for job in (active, ready)}), patch.object(studio, 'POWER_INTERRUPTED_JOBS', set()), patch.object(studio, 'store_job'):
            self.assertEqual(studio.record_power_event('wake')['affected_jobs'], 1)
            self.assertIn(active['id'], studio.POWER_INTERRUPTED_JOBS)
            studio.check_training_power(ready)
            with self.assertRaisesRegex(studio.TrainingWindowInterrupted, 'sleep/wake was reported'):
                studio.check_training_power(active)
            with self.assertRaises(ValueError): studio.record_power_event('unknown')

    def test_power_event_returns_waiting_worker_to_approval_without_trainer(self):
        job = {'id': 'power-wait', 'status': 'queued', 'idle': True}
        with patch.object(studio, 'POWER_INTERRUPTED_JOBS', {job['id']}), patch.object(studio, 'store_job'), patch.object(studio.recipe_contracts, 'execute') as execute:
            studio.run(job)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertIn('approve training again', job['error'])
            execute.assert_not_called()

    def test_power_event_during_final_evaluation_prevents_preview_persistence(self):
        import tempfile
        from pathlib import Path
        job = {'id': 'late-power', 'status': 'queued', 'idle': False, 'recipe': 'text_to_image', 'target': 0.8}
        rows = studio.image_recipe.dataset()
        def finish(*args, **kwargs):
            studio.record_power_event('wake')
            return {'format': 'fixture'}, rows, {'passed': True}
        with tempfile.TemporaryDirectory() as folder, patch.object(studio, 'ROOT', Path(folder)), patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'CANDIDATES', {}), patch.object(studio, 'POWER_INTERRUPTED_JOBS', set()), patch.object(studio, 'store_job'), patch.object(studio.training_resources, 'check', return_value={}), patch.object(studio.recipe_contracts, 'execute', side_effect=finish):
            studio.run(job)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertIn('sleep/wake was reported', job['error'])
            self.assertIn(job['id'], studio.TRAINING_DATA)
            self.assertNotIn(job['id'], studio.CANDIDATES)
            self.assertFalse(list(Path(folder).rglob('candidate.*')))

    def test_clock_gap_during_final_evaluation_prevents_preview_persistence(self):
        job = {'id': 'late-clock', 'status': 'queued', 'idle': False, 'recipe': 'text_to_image', 'target': 0.8}
        rows = studio.image_recipe.dataset()
        with patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'CANDIDATES', {}), patch.object(studio, 'store_job'), patch.object(studio.training_resources, 'check', return_value={}), patch.object(studio, 'training_clock', side_effect=[(100., 10.), (160., 11.)]), patch.object(studio.recipe_contracts, 'execute', return_value=({}, rows, {})):
            studio.run(job)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertIn('system-clock change', job['error'])
            self.assertIn(job['id'], studio.TRAINING_DATA)
            self.assertNotIn(job['id'], studio.CANDIDATES)
