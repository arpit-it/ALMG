from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from backend import decoder_corpus_benchmark_evaluation as evaluation, decoder_corpus_benchmarks as benchmarks, decoder_corpus_isolated as isolated
from test_decoder_corpus_benchmarks import documents
from test_decoder_corpus_optimizer import corpus


class BenchmarkEvaluationTest(unittest.TestCase):
    def test_baseline_controls_validate_before_any_artifact_access(self):
        for value in (None,0,1,'true',[],{}):
            with self.assertRaises(ValueError):evaluation.evaluate(Path('/unused'),'bench','model',baseline_initialization=value)
        with self.assertRaises(ValueError):evaluation.evaluate(Path('/unused'),'bench','model','baseline',baseline_initialization=True)

    def test_comparison_requires_identical_benchmark_protocol_runtime_and_producer(self):
        original={'benchmark_binding':{'id':'same'},'protocol_revision':'one','runtime':{},'implementation_sha256':'same'}
        for field,value in (('benchmark_binding',{}),('protocol_revision','two'),('runtime',{'numpy':'other'}),('implementation_sha256','changed')):
            changed={**original,field:value}
            with self.assertRaises(ValueError):evaluation.compare(original,changed)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires completed models scored on evaluation-only windows')
    def test_real_benchmark_scores_baselines_and_preserves_all_artifacts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root);models=[]
            for kind in ('sgd','adamw'):
                config={**base,'steps':10,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                models.append(isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex))
            docs=documents();benchmark=benchmarks.save(root,saved['id'],True,docs,benchmarks.review(root,saved['id'],docs))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=evaluation.evaluate(root,benchmark['id'],models[1]['id'],models[0]['id'])
            self.assertEqual(report['benchmark_binding']['revision'],benchmark['revision'])
            self.assertEqual(report['metrics']['heldout']['target_tokens'],7)
            self.assertEqual(report['metrics']['heldout']['padding_positions'],1)
            self.assertEqual(report['metrics']['generation']['generated_tokens'],4)
            for field in ('training_approved','release_approved','language_quality_validated','independent_evaluation_certified'):self.assertFalse(report[field])
            self.assertEqual(report,evaluation.evaluate(root,benchmark['id'],models[1]['id'],models[0]['id']))
            initial=evaluation.evaluate(root,benchmark['id'],models[1]['id'],baseline_initialization=True)
            self.assertEqual(initial['comparison']['baseline_source']['initialization_id'],source['id'])
            same=evaluation.evaluate(root,benchmark['id'],models[1]['id'],models[1]['id'])
            self.assertTrue(all(value==0 for section in same['comparison']['candidate_minus_baseline'].values() for value in section.values() if value is not None))
            changed=deepcopy(report);changed['benchmark_binding']['revision']='changed'
            with self.assertRaises(ValueError):evaluation.compare(report,changed)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            path=root/'decoder-corpus-benchmarks'/benchmark['id']/'windows.json';original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):evaluation.evaluate(root,benchmark['id'],models[1]['id'])
            finally:path.write_bytes(original)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
