from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_benchmark_results as results, decoder_corpus_benchmark_evaluation as scoring, decoder_corpus_benchmarks as benchmarks, decoder_corpus_isolated as isolated
from test_decoder_corpus_benchmarks import documents
from test_decoder_corpus_optimizer import corpus


class BenchmarkResultTest(unittest.TestCase):
    def test_unconfirmed_save_and_invalid_ids_do_not_write(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):results.save(root,'a'*32,'b'*32,False,{})
            for value in (None,'invalid',3):
                with self.assertRaises(ValueError):results.read(root,value)
                with self.assertRaises(ValueError):results.history(root,value,'b'*32)
            self.assertEqual(list(root.iterdir()),[])

    def test_malformed_reports_rejected(self):
        for report in ({},[],None):
            with self.assertRaises(ValueError):results._validate(report)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires a real completed model and evaluation-only benchmark')
    def test_confirmed_snapshot_reopen_scoped_history_and_tamper_recovery(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,inputs,base=corpus(root);config={**base,'steps':10}
            model=isolated.run(root,True,source,inputs,config,isolated.review(root,source,inputs,config),uuid.uuid4().hex)
            docs=documents();benchmark=benchmarks.save(root,inputs['id'],True,docs,benchmarks.review(root,inputs['id'],docs))
            reviewed=scoring.evaluate(root,benchmark['id'],model['id'],baseline_initialization=True)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            stale=deepcopy(reviewed);stale['limitations']='Changed.'
            with self.assertRaises(ValueError):results.save(root,benchmark['id'],model['id'],True,stale,baseline_initialization=True)
            with self.assertRaises(ValueError):results.save(root,benchmark['id'],model['id'],True,reviewed)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            saved=results.save(root,benchmark['id'],model['id'],True,reviewed,baseline_initialization=True)
            self.assertEqual(saved['report'],reviewed)
            with patch.object(scoring,'evaluate',side_effect=AssertionError('Historical snapshots must not be recomputed.')):
                self.assertEqual(results.read(root,saved['record']['id']),saved)
                self.assertEqual(results.history(root,benchmark['id'],model['id']),[saved['record']])
            self.assertEqual(results.history(root,'c'*32,model['id']),[])
            self.assertEqual(results.history(root,benchmark['id'],'d'*32),[])
            self.assertFalse(saved['record']['release_approved']);self.assertFalse(saved['report']['language_quality_validated'])
            path=root/'decoder-benchmark-evaluations'/saved['record']['id']/'report.json';original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):results.read(root,saved['record']['id'])
                self.assertEqual(results.history(root,benchmark['id'],model['id']),[])
            finally:path.write_bytes(original)
            self.assertEqual(results.read(root,saved['record']['id']),saved)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
