import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
import numpy as np
from backend import decoder_corpus_generation_evaluation as evaluation, decoder_corpus_isolated as isolated
from backend.decoder_tokenizer import Tokenizer
from test_decoder_corpus_optimizer import corpus


class GenerationEvaluationTest(unittest.TestCase):
    def test_free_running_uses_generated_history_and_excludes_padding(self):
        class Model:
            config={'context_length':2}
            def __init__(self):self.calls=[]
            def logits(self,inputs):
                self.calls.append(inputs.tolist()[0]);scores=np.zeros((1,inputs.shape[1],4),dtype=np.float32)
                scores[0,-1,2 if inputs[0,-1] in (0,2) else 3]=1
                return scores
        model=Model();tokenizer=Tokenizer(['a','b','c','d'])
        rows=[{'inputs':[0,1,3,0],'targets':[1,3,0,0],'target_mask':[1,1,0,0]}]
        result=evaluation.score_split(model,rows,tokenizer)
        self.assertEqual(model.calls,[[0],[0,2]])
        self.assertEqual(result['examples'][0]['generated_token_ids'],[2,2])
        self.assertEqual(result['examples'][0]['reference_token_ids'],[1,3])
        self.assertEqual(result['reference_target_tokens'],2);self.assertEqual(result['generated_tokens'],2)
        self.assertEqual(result['free_running_reference_token_match_rate'],0)
        self.assertEqual(result['adjacent_repeat_rate'],1);self.assertEqual(result['exact_continuation_matches'],0)
        self.assertEqual(result['examples'][0]['generated_text'],'c c')

    def test_fixed_window_and_generation_caps_and_single_token_repeat_rate(self):
        class Model:
            config={'context_length':2}
            def logits(self,inputs):return np.zeros((1,inputs.shape[1],4),dtype=np.float32)
        tokenizer=Tokenizer(['a','b','c','d']);row={'inputs':[0]*8,'targets':[0]*8,'target_mask':[1]*8}
        result=evaluation.score_split(Model(),[row]*20,tokenizer)
        self.assertEqual(result['window_count'],8);self.assertEqual(result['generated_tokens'],32)
        self.assertEqual(result['exact_continuation_match_rate'],1)
        self.assertEqual(result['examples'][0]['matching_prefix_tokens'],4)
        one=evaluation.score_split(Model(),[{'inputs':[0],'targets':[0],'target_mask':[1]}],tokenizer)
        self.assertIsNone(one['adjacent_repeat_rate']);self.assertEqual(one['generated_transitions'],0)

    def test_invalid_logits_empty_reference_and_nonprefix_masks_rejected(self):
        class Model:
            config={'context_length':2}
            def logits(self,inputs):return np.full((1,inputs.shape[1],4),np.nan)
        tokenizer=Tokenizer(['a','b','c','d'])
        for row in ({'inputs':[0],'targets':[0],'target_mask':[1]},
                    {'inputs':[0],'targets':[0],'target_mask':[0]},
                    {'inputs':[0,1],'targets':[1,2],'target_mask':[0,1]}):
            with self.assertRaises(ValueError):evaluation.score_split(Model(),[row],tokenizer)

    def test_comparison_requires_identical_protocol_and_data(self):
        report={'protocol_revision':'one','evaluation_data_binding':{'windows_sha256':'same'}}
        for other in ({**report,'protocol_revision':'two'},{**report,'evaluation_data_binding':{}}):
            with self.assertRaises(ValueError):evaluation.compare(report,other)

    def test_invalid_baseline_options_rejected(self):
        for value in (None,0,1,'true',[],{}):
            with self.assertRaises(ValueError):evaluation.evaluate(Path('/unused'),'unused',baseline_initialization=value)
        with self.assertRaises(ValueError):evaluation.evaluate(Path('/unused'),'unused','baseline',baseline_initialization=True)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires completed corpus models and saved initialization')
    def test_real_generation_baselines_reload_and_preserve_sources(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root);records=[]
            for kind in ('sgd','adamw'):
                config={**base,'steps':10,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                records.append(isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for record in records:
                report=evaluation.evaluate(root,record['id'],baseline_initialization=True)
                self.assertEqual(report['comparison']['baseline_source']['initialization_id'],source['id'])
                self.assertFalse(report['language_quality_validated']);self.assertFalse(report['training_approved']);self.assertFalse(report['release_approved'])
                self.assertEqual(report,evaluation.evaluate(root,record['id'],baseline_initialization=True))
                for split,metrics in report['metrics'].items():
                    self.assertEqual(metrics['window_count'],saved['review']['splits'][split]['windows'])
                    self.assertTrue(all(len(row['generated_token_ids'])<=4 for row in metrics['examples']))
                same=evaluation.evaluate(root,record['id'],record['id'])
                self.assertTrue(all(value==0 for row in same['comparison']['candidate_minus_baseline'].values() for value in row.values() if value is not None))
            compared=evaluation.evaluate(root,records[1]['id'],records[0]['id'])
            self.assertEqual(compared['comparison']['baseline_source']['record_id'],records[0]['id'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
