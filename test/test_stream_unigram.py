import base64
import importlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from backend import decoder_stream_unigram as fits,decoder_stream_unigram_candidates as candidates,decoder_stream_indexes as indexes,decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_permissions as permissions,decoder_stream_learned_windows as windows
from backend.decoder_unigram import UnigramTokenizer
from test_stream_iterative_bpe import fixture


def finish(worker,root,record):
    while record['status']!='complete':record=worker.step(root,record['id'],True)
    return record


def setup(root):
    index=fixture(root);candidate=finish(candidates,root,candidates.begin(root,index['id'],True,candidates.review(root,index['id'],64)))
    return index,candidate


class FullSplitUnigramTests(unittest.TestCase):
    def test_five_updates_match_sample_oracle_and_resume_exact_partial_expected_counts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,candidate=setup(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            record=fits.begin(root,candidate['id'],True,fits.review(root,candidate['id']))
            with patch.object(fits,'MAX_BATCH_RECORDS',2):record=fits.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],2);self.assertTrue(any(record['expected_counts']))
            importlib.reload(fits);self.assertEqual(fits.read(root,record['id']),record)
            record=finish(fits,root,record)
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:train=[text for text, in db.execute('SELECT text FROM documents WHERE split=? ORDER BY group_sha256',('train',))]
            oracle=UnigramTokenizer.fit(train,64);codec=fits.StreamUnigram.restore(json.loads((fits._folder(root,record['id'])/'artifacts'/'tokenizer.json').read_text()))
            self.assertEqual(codec.pieces,oracle.pieces);self.assertEqual(codec.alphabet,oracle.alphabet)
            for actual,expected in zip(codec.probabilities,oracle.probabilities):self.assertAlmostEqual(actual,expected,places=12)
            for actual,expected in zip(record['history'],oracle.history):self.assertAlmostEqual(actual,expected,places=8)
            self.assertEqual(record['completed_passes'],6);self.assertEqual(record['em_updates'],5)
            self.assertTrue(all(after>=before-1e-6 for before,after in zip(record['history'],record['history'][1:])))
            self.assertAlmostEqual(math.fsum(codec.probabilities),1)
            for text in train+['banana '*800]:self.assertEqual(codec.decode(codec.encode(text)),text)
            with self.assertRaises(ValueError):codec.encode('Ω')
            report=finish(scans,root,scans.begin(root,record['id'],True,record,'unigram'))
            self.assertEqual(report['fit_kind'],'unigram');self.assertEqual(report['processed_records'],index['unique_records']);self.assertFalse(report['tokenizer_refitted'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            exported=fits.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:self.assertEqual(json.loads(archive.read('tokenizer.json')),codec.artifact())
            self.assertFalse(record['model_training_enabled']);self.assertFalse(record['release_approved']);self.assertEqual(fits.step(root,record['id'],True),record)

    def test_likelihood_decrease_and_nonfinite_expectations_preserve_progress(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,candidate=setup(root);record=fits.begin(root,candidate['id'],True,fits.review(root,candidate['id']))
            count=len(candidate['initializer']['pieces'])
            with patch.object(fits.StreamUnigram,'_expected',return_value=(0.,[1.]*count)):record=fits.step(root,record['id'],True)
            self.assertEqual(record['completed_passes'],1)
            with patch.object(fits.StreamUnigram,'_expected',return_value=(-1.,[1.]*count)):
                with self.assertRaisesRegex(ValueError,'likelihood decreased'):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            with patch.object(fits.StreamUnigram,'_expected',return_value=(float('nan'),[1.]*count)):
                with self.assertRaisesRegex(ValueError,'invalid'):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)

    def test_consent_binding_transaction_and_publication_recovery(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,candidate=setup(root);review=fits.review(root,candidate['id'])
            with self.assertRaises(ValueError):fits.begin(root,candidate['id'],False,review)
            with self.assertRaises(ValueError):fits.begin(root,candidate['id'],True,{})
            record=fits.begin(root,candidate['id'],True,review)
            with patch.object(fits,'_write',side_effect=OSError('transaction interrupted')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            while record['completed_passes']<5:record=fits.step(root,record['id'],True)
            with patch.object(fits,'_publish',side_effect=OSError('publication interrupted')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            pending=fits.read(root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
            complete=fits.step(root,record['id'],True);self.assertEqual(complete['probabilities'],pending['probabilities'])
            other=fits.begin(root,candidate['id'],True,fits.review(root,candidate['id']));old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA')
            with self.assertRaisesRegex(ValueError,'permission review changed'):fits.step(root,other['id'],True)
            self.assertEqual(fits.read(root,other['id']),other)

    def test_mid_batch_source_rewrite_rejects_without_advancing_expected_counts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,candidate=setup(root);record=fits.begin(root,candidate['id'],True,fits.review(root,candidate['id']))
            path=candidates.sources.streams.folder(root,index['source_id'])/'source.bin';binding=fits._binding;calls=0
            def changed(*args):
                nonlocal calls
                calls+=1
                if calls==2:path.write_bytes(path.read_bytes())
                return binding(*args)
            with patch.object(fits,'_binding',side_effect=changed):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
