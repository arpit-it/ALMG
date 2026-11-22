import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_storage_profile as storage, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class CorpusStorageProfileTest(unittest.TestCase):
    def test_measure_rejects_changed_artifact_or_manifest(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'artifact';path.write_bytes(b'weights')
            self.assertEqual(storage._measure(path,expected_sha=hashlib.sha256(b'weights').hexdigest())['bytes'],7)
            with self.assertRaises(ValueError):storage._measure(path,expected_sha='0'*64)
            path.write_text('{"revision":"changed"}')
            with self.assertRaises(ValueError):storage._measure(path,expected_record={'revision':'original'})

    def test_measure_has_bounded_reads(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'artifact';path.write_bytes(b'x'*33)
            with patch.object(storage,'MAX_ARTIFACT_BYTES',32):
                with self.assertRaises(ValueError):storage._measure(path)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real corpus run and retained progress snapshots')
    def test_actual_storage_counts_provenance_incomplete_scans_and_readonly(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,c=corpus(root)
            run=isolated.run(root,True,source,saved,c,isolated.review(root,source,saved,c),uuid.uuid4().hex)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=storage.profile(root,run['id'])
            self.assertTrue(report['inventory_complete']);self.assertEqual(report['retained_progress_count'],8)
            expected=sum(len(data) for path,data in before.items() if path.is_relative_to(root/'decoder-corpus-optimizer-runs'/run['id']) or path.is_relative_to(root/storage.interruptions.DIRECTORY))
            self.assertEqual(report['total_bytes'],expected)
            self.assertEqual(sum(report['category_bytes'].values()),expected)
            self.assertTrue(report['reserve_covers_observed_progress']);self.assertFalse(report['training_approved'])
            self.assertEqual(report['revision'],storage.digest({k:v for k,v in report.items() if k!='revision'}))
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            with patch.object(storage,'MAX_PROGRESS_RECORDS',0):
                incomplete=storage.profile(root,run['id']);self.assertTrue(incomplete['scan_truncated']);self.assertFalse(incomplete['inventory_complete']);self.assertIsNone(incomplete['reserve_covers_observed_progress'])
            unknown=root/storage.interruptions.DIRECTORY/('f'*32);unknown.mkdir();(unknown/'record.json').write_text('incomplete')
            incomplete=storage.profile(root,run['id']);self.assertFalse(incomplete['inventory_complete']);self.assertEqual(len(incomplete['unclassified_progress_records']),1)
            self.assertIsNone(incomplete['reserve_covers_observed_progress'])
            (unknown/'record.json').write_text('{}')
            incomplete=storage.profile(root,run['id']);self.assertFalse(incomplete['inventory_complete']);self.assertEqual(incomplete['unclassified_progress_records'][0]['reason'],'missing_or_invalid_source_binding')
            path=next((root/storage.interruptions.DIRECTORY).glob('*/optimizer.json'));path.write_text('{}')
            with self.assertRaises(ValueError):storage.profile(root,run['id'])
