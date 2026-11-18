import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend import studio, training_resources as resources


class TrainingResourcesTest(unittest.TestCase):
    def test_macos_memory_uses_page_size_and_reclaimable_pages(self):
        self.assertEqual(resources.memory_from_vm_stat('Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 10.\nPages inactive: 20.\nPages speculative: 3.\n'), 33 * 16384)
        with self.assertRaises(ValueError): resources.memory_from_vm_stat('bad output')

    def test_estimate_and_low_memory_disk_failures_use_local_fixtures(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(resources, 'available_memory', return_value=1024 * resources.MIB), patch.object(resources.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024 * resources.MIB)):
            result = resources.check([{'text': 'fixture'}], Path(folder) / 'future' / 'runs')
            self.assertGreater(result['estimated_memory_reserve_bytes'], 256 * resources.MIB)
            with patch.object(resources, 'available_memory', return_value=1):
                with self.assertRaisesRegex(resources.ResourceUnavailable, 'Close other apps'): resources.check([], Path(folder))
            with patch.object(resources.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(resources.ResourceUnavailable, 'Free space'): resources.check([], Path(folder))

    def test_low_resources_keep_approval_and_do_not_queue_worker(self):
        job = {'id': 'resource-fixture', 'status': 'dataset_ready', 'recipe': 'text_to_image'}
        body = json.dumps({'target': 0.8, 'idle': False}).encode()
        handler = Mock(path='/jobs/resource-fixture/start', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        with patch.object(studio, 'JOBS', {job['id']: job}), patch.object(studio, 'store_job'), patch.object(studio.threading, 'Thread') as worker, patch.object(resources, 'check', side_effect=resources.ResourceUnavailable('Not enough available memory')):
            studio.Handler.do_POST(handler)
        self.assertEqual(job['status'], 'dataset_ready')
        self.assertEqual(handler.respond.call_args.args[1], 400)
        worker.assert_not_called()

    def test_resource_loss_after_queue_returns_to_approval_and_retains_dataset(self):
        job = {'id': 'queued-fixture', 'status': 'queued', 'idle': False}
        rows = [{'text': 'local fixture'}]
        with patch.object(studio, 'TRAINING_DATA', {job['id']: rows}), patch.object(studio, 'store_job'), patch.object(resources, 'check', side_effect=resources.ResourceUnavailable('Low disk')), patch.object(studio.recipe_contracts, 'execute') as execute:
            studio.run(job)
            self.assertEqual(job['status'], 'dataset_ready')
            self.assertEqual(studio.TRAINING_DATA[job['id']], rows)
            execute.assert_not_called()
