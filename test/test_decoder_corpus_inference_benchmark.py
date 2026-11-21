import os
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
import unittest
import uuid
import numpy as np
from backend import decoder_corpus_inference_benchmark as benchmark, decoder_corpus_isolated as isolated
from backend.run_manifest import digest
from test_decoder_corpus_optimizer import corpus


class InferenceBenchmarkTest(unittest.TestCase):
    def test_observed_time_arithmetic_and_greedy_context_feedback(self):
        class Model:
            config={'context_length':2,'vocab_size':4}
            def __init__(self):self.contexts=[]
            def logits(self,inputs):
                self.contexts.append(inputs.tolist()[0]);scores=np.zeros((1,inputs.shape[1],4),dtype=np.float32)
                scores[0,-1,(inputs[0,-1]+1)%4]=1;return scores
        model=Model();clock=iter([100,150,1100])
        result=benchmark._sample(model,[1,2],lambda:next(clock))
        self.assertEqual(result['generated_token_ids'],[3,0,1,2,3,0,1,2])
        self.assertEqual(model.contexts[:3],[[1,2],[2,3],[3,0]])
        self.assertTrue(all(len(context)==2 for context in model.contexts))
        self.assertEqual(result['elapsed_ns'],1000);self.assertEqual(result['first_token_ns'],50)
        self.assertEqual(result['tokens_per_second'],8e6)
        self.assertEqual(result['subsequent_tokens_per_second'],7e9/950)

    def test_nonpositive_or_nonmonotonic_clocks_rejected(self):
        class Model:
            config={'context_length':2,'vocab_size':4}
            def logits(self,inputs):return np.zeros((1,inputs.shape[1],4),dtype=np.float32)
        for values in ([0,0,10],[0,10,10],[10,15,9]):
            clock=iter(values)
            with self.assertRaises(ValueError):benchmark._sample(Model(),[0],lambda:next(clock))

    def test_invalid_logits_rejected(self):
        class Model:
            config={'context_length':2,'vocab_size':4}
            def __init__(self,scores):self.scores=scores
            def logits(self,inputs):return self.scores
        for scores in (np.zeros((1,1,3)),np.full((1,1,4),np.nan),np.full((1,1,4),np.inf)):
            with self.assertRaises(ValueError):benchmark._sample(Model(scores),[0],lambda:1)

    def test_invalid_run_id_rejected(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):benchmark.benchmark(Path(temporary),'invalid')
            self.assertEqual(list(Path(temporary).iterdir()),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real completed corpus models')
    def test_real_cpu_samples_sizes_and_read_only_source_binding(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            for kind in ('sgd','adamw'):
                config={**base,'steps':10,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                record=isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                report=benchmark.benchmark(root,record['id']);samples=report['samples'];metrics=report['metrics']
                self.assertEqual(len(samples),3);self.assertEqual(metrics['generated_tokens'],24)
                self.assertEqual(metrics['elapsed_ns'],sum(s['elapsed_ns'] for s in samples))
                self.assertEqual(metrics['tokens_per_second'],24e9/metrics['elapsed_ns'])
                self.assertEqual(metrics['first_token_ns_median'],statistics.median(s['first_token_ns'] for s in samples))
                self.assertTrue(all(s['elapsed_ns']>s['first_token_ns']>0 for s in samples))
                self.assertTrue(all(s['generated_token_ids']==report['warmup']['generated_token_ids'] for s in samples))
                self.assertEqual(report['source']['record_revision'],record['revision'])
                self.assertEqual(report['model_size']['parameter_count'],source['actual_parameter_count'])
                self.assertEqual(report['model_size']['parameter_tensor_bytes'],4*source['actual_parameter_count'])
                self.assertEqual(report['model_size']['saved_model_artifact_bytes'],(root/'decoder-corpus-optimizer-runs'/record['id']/'trained-model.json').stat().st_size)
                self.assertIsNone(report['model_size']['peak_memory_bytes'])
                for field in ('training_approved','release_approved','language_quality_validated'):self.assertFalse(report[field])
                self.assertEqual(report['revision'],digest({k:v for k,v in report.items() if k!='revision'}))
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
