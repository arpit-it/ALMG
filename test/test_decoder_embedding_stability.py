import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
import numpy as np
from backend import decoder_architecture_backward as backward, decoder_corpus_isolated as isolated
from test_decoder_corpus_four_rows import four_rows


@unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual Metal embedding gradients and checkpoint replay')
class EmbeddingStabilityTest(unittest.TestCase):
    def test_lookup_matches_gather_and_repeated_token_gradient_matches_cpu_sum(self):
        import mlx.core as mx
        with mx.stream(mx.gpu):
            rng=np.random.default_rng(7);embedding=rng.normal(0,.02,(4,8)).astype(np.float32)
            tokens=np.arange(32,dtype=np.int32).reshape(4,8)%4;upstream=rng.normal(0,.01,(4,8,8)).astype(np.float32)
            x=mx.array(tokens)
            for dtype in (mx.float32,):
                p=mx.array(embedding,dtype=dtype)
                actual=backward.token_embeddings(p,x,mx);expected=p[x];mx.eval(actual,expected)
                np.testing.assert_array_equal(np.array(actual),np.array(expected))
            def loss(p):return mx.sum(backward.token_embeddings(p,x,mx)*mx.array(upstream))
            actual=mx.grad(loss)(mx.array(embedding));mx.eval(actual)
            expected=np.zeros((4,8),dtype=np.float64)
            for token,weight in zip(tokens.reshape(-1),upstream.reshape(-1,8)):expected[token]+=weight
            np.testing.assert_allclose(np.array(actual),expected.astype(np.float32),rtol=1e-5,atol=1e-7)

    def test_identical_four_row_fp32_gradients_repeat_exactly(self):
        import mlx.core as mx
        with mx.stream(mx.gpu), TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,config=four_rows(root);training=isolated.training
            _,current,_,windows,_=training._source(root,source,saved)
            model=training.PlannedDecoder.load(training.hardware.initializations._folder(root,source['plan_id'])/source['id']/'model.json')
            _,arrays=training.batch_arrays(windows['train'],10,4);x,y,mask=[mx.array(a) for a in arrays]
            gradient=backward.metal_functions(current['config'],mx)[2];first=None
            for _ in range(64):
                values=gradient({name:mx.array(value.copy()) for name,value in model.parameters.items()},x,y,mask);mx.eval(values)
                actual={name:np.array(value) for name,value in values.items()}
                if first is None:first=actual
                for name in actual:np.testing.assert_array_equal(actual[name],first[name],err_msg=name)

    def test_four_row_checkpoint_and_continuation_repeat_bit_exactly_for_both_optimizers(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=four_rows(root);seen={}
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for repeat in range(2):
                for kind in ('sgd','adamw'):
                    for accumulation in (1,2,4):
                        config={**base,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.,'gradient_accumulation_steps':accumulation}
                        record=isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex)
                        self.assertEqual(record['checkpoint_parameter_max_error'],0.)
                        self.assertEqual(record['checkpoint_optimizer_max_error'],0.)
                        hashes=tuple(record['files'][name] for name in ('trained-model.json','step-10/model.json','step-10/optimizer.json'))
                        if repeat:self.assertEqual(hashes,seen[(kind,accumulation)])
                        else:seen[(kind,accumulation)]=hashes
                        continued=isolated.run_continuation(root,record['id'],True,isolated.review_continuation(root,record['id']),uuid.uuid4().hex)
                        self.assertEqual(continued['reference_parameter_max_error'],0.)
                        self.assertEqual(continued['generated_token_ids'],record['generated_token_ids'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
