import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_preparations as drafts, decoder_datasets as datasets


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.documents = [{'name':str(i), 'text':f'Local fixture document {i} with café text'} for i in range(3)]

    def test_saved_inputs_resume_explicitly_after_reload_and_are_idempotent(self):
        record = drafts.create(self.root, self.documents, True, 'utf8_bytes')
        self.assertFalse((self.root / 'decoder-datasets').exists())
        self.assertEqual(drafts.list_drafts(self.root), [record])
        self.assertEqual(drafts.read(self.root, record['id']), record)
        snapshot = (drafts.folder(self.root, record['id']) / 'inputs.json').read_bytes()
        dataset = drafts.resume(self.root, record['id'], True)
        self.assertEqual(dataset['id'], record['id'])
        self.assertEqual(dataset['derivation']['inputs_sha256'], record['inputs_sha256'])
        self.assertEqual(drafts.resume(self.root, record['id'], True), dataset)
        self.assertEqual(len(list((self.root / 'decoder-datasets').iterdir())), 1)
        self.assertEqual(drafts.read(self.root, record['id'])['status'], 'complete')
        self.assertEqual(snapshot, (drafts.folder(self.root, record['id']) / 'inputs.json').read_bytes())
        self.assertFalse((self.root / 'decoder-trials').exists())

    def test_interrupted_completion_recovers_published_dataset_without_duplicate(self):
        record = drafts.create(self.root, self.documents, True)
        with patch.object(drafts, '_write_record', side_effect=OSError('interrupted completion')):
            with self.assertRaises(OSError):
                drafts.resume(self.root, record['id'], True)
        dataset = datasets.read(self.root, record['id'])
        before = {p.name:p.read_bytes() for p in (self.root / 'decoder-datasets' / record['id']).iterdir()}
        self.assertEqual(drafts.read(self.root, record['id'])['status'], 'awaiting_preparation')
        with patch.object(datasets, 'prepare', side_effect=AssertionError('must recover existing output')):
            self.assertEqual(drafts.resume(self.root, record['id'], True), dataset)
        self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root / 'decoder-datasets' / record['id']).iterdir()})

    def test_consent_implementation_changes_and_corrupt_snapshot_do_not_publish(self):
        for consent in (False, None, 1):
            with self.assertRaises(ValueError):
                drafts.create(self.root, self.documents, consent)
        record = drafts.create(self.root, self.documents, True)
        with self.assertRaises(ValueError): drafts.resume(self.root, record['id'], False)
        with patch.object(drafts, 'implementation', return_value='changed'):
            self.assertFalse(drafts.read(self.root, record['id'])['implementation_current'])
            with self.assertRaisesRegex(ValueError, 'implementation changed'):
                drafts.resume(self.root, record['id'], True)
        (drafts.folder(self.root, record['id']) / 'inputs.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            drafts.resume(self.root, record['id'], True)
        self.assertEqual(drafts.list_drafts(self.root), [])
        self.assertFalse((self.root / 'decoder-datasets').exists())

    def test_invalid_inputs_leave_no_draft_and_failed_preparation_can_retry(self):
        with self.assertRaises(ValueError): drafts.create(self.root, [], True)
        self.assertFalse((self.root / 'decoder-preparations').exists())
        record = drafts.create(self.root, self.documents, True)
        with patch.object(datasets, 'prepare', side_effect=OSError('temporary interruption')):
            with self.assertRaises(OSError): drafts.resume(self.root, record['id'], True)
        self.assertEqual(drafts.read(self.root, record['id'])['status'], 'awaiting_preparation')
        self.assertEqual(drafts.resume(self.root, record['id'], True)['id'], record['id'])


if __name__ == '__main__': unittest.main()
