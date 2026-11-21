from copy import deepcopy
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
import numpy as np
from backend import decoder_corpus_evaluation as evaluation, decoder_corpus_isolated as isolated
from test_decoder_corpus_optimizer import corpus


class HeldoutEvaluationTest(unittest.TestCase):
    def test_masked_targets_weight_loss_and_failure_examples_exclude_padding(self):
        class Model:
            def logits(self,inputs):
                scores=np.zeros((1,2,4),dtype=np.float32)
                if inputs[0,0]==0:scores[0,1]=[1000,0,0,0]
                return scores
        windows=[{'inputs':[0,0],'targets':[0,3],'target_mask':[1,0]},
                 {'inputs':[1,1],'targets':[1,2],'target_mask':[1,1]}]
        result=evaluation.score_split(Model(),windows,['a','b','c','d'])
        self.assertAlmostEqual(result['cross_entropy_nats_per_target'],math.log(4))
        self.assertAlmostEqual(result['perplexity'],4.)
        self.assertEqual(result['target_tokens'],3);self.assertEqual(result['dense_positions'],4);self.assertEqual(result['padding_positions'],1)
        self.assertEqual(result['teacher_forced_token_accuracy'],1/3)
        self.assertEqual([(r['window_index'],r['position']) for r in result['failure_examples']],[(1,0),(1,1)])

    def test_perplexity_overflow_and_invalid_values_are_explicit(self):
        self.assertEqual(evaluation.perplexity(0),(1.,'available'))
        self.assertEqual(evaluation.perplexity(1000),(None,'overflow_unavailable'))
        for value in (True,-1,float('nan'),float('inf'),'1'):
            with self.assertRaises(ValueError):evaluation.perplexity(value)

    def test_baseline_requires_identical_protocol_and_data_binding(self):
        report={'protocol_revision':'one','evaluation_data_binding':{'windows_sha256':'same'}}
        for changed in ({**report,'protocol_revision':'other'},{**report,'evaluation_data_binding':{'windows_sha256':'different'}}):
            with self.assertRaises(ValueError):evaluation.compare(report,changed)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real completed two-row models with saved held-out corpus')
    def test_real_models_re_evaluate_compare_and_preserve_all_source_artifacts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            records=[]
            for kind,steps in (('sgd',10),('adamw',20)):
                config={**base,'optimizer':kind,'steps':steps,'learning_rate':.001,'batch_size':2,'gradient_accumulation_steps':2,'weight_decay':.01 if kind=='adamw' else 0.}
                records.append(isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=evaluation.evaluate(root,records[1]['id'],records[0]['id'])
            self.assertEqual(set(report['metrics']),{'validation','test'})
            for split in ('validation','test'):
                metrics=report['metrics'][split]
                self.assertAlmostEqual(metrics['cross_entropy_nats_per_target'],records[1]['final_losses'][split],places=9)
                self.assertAlmostEqual(metrics['perplexity'],math.exp(records[1]['final_losses'][split]),places=9)
                self.assertEqual(metrics['target_tokens'],saved['review']['splits'][split]['target_tokens'])
                self.assertLessEqual(len(metrics['failure_examples']),8)
                difference=report['comparison']['candidate_minus_baseline'][split]['cross_entropy_nats_per_target']
                self.assertAlmostEqual(difference,records[1]['final_losses'][split]-records[0]['final_losses'][split],places=9)
            self.assertFalse(report['training_approved']);self.assertFalse(report['release_approved']);self.assertFalse(report['language_quality_validated'])
            self.assertEqual(report,evaluation.evaluate(root,records[1]['id'],records[0]['id']))
            report['protocol']['splits'].append('train')
            self.assertEqual(evaluation.evaluate(root,records[1]['id'])['protocol']['splits'],['validation','test'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
