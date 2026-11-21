from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_benchmark_comparisons as comparisons, decoder_corpus_benchmark_results as results, decoder_corpus_benchmark_evaluation as scoring, decoder_corpus_benchmarks as benchmarks, decoder_corpus_isolated as isolated
from test_decoder_corpus_benchmarks import documents
from test_decoder_corpus_optimizer import corpus


def snapshot():
    report={'benchmark_binding':{},'protocol_revision':'same','runtime':{},'implementation_sha256':'same',
            'metrics':{section:{key:1 for key in keys} for section,keys in
                (('heldout',('window_count','target_tokens','dense_positions','padding_positions','cross_entropy_nats_per_target','perplexity','teacher_forced_token_accuracy')),
                 ('generation',('window_count','reference_target_tokens','generated_tokens','generated_transitions','exact_continuation_match_rate','free_running_reference_token_match_rate','adjacent_repeat_rate')))},'source':{}}
    return {'record':{},'report':report}


class BenchmarkComparisonTest(unittest.TestCase):
    def test_invalid_snapshot_ids_do_not_write(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):comparisons.compare(root,'invalid','a'*32)
            self.assertEqual(list(root.iterdir()),[])

    def test_saved_metric_coverage_must_match(self):
        for section,key in (('heldout','target_tokens'),('generation','generated_tokens')):
            left=snapshot();right=deepcopy(left);right['report']['metrics'][section][key]+=1
            with patch.object(results,'read',side_effect=[left,right]),self.assertRaisesRegex(ValueError,'coverage'):
                comparisons.compare(Path('/unused'),'a'*32,'b'*32)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real saved benchmark scoring reports')
    def test_real_historical_comparison_deltas_self_comparison_and_immutability(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,inputs,base=corpus(root);docs=documents()
            benchmark=benchmarks.save(root,inputs['id'],True,docs,benchmarks.review(root,inputs['id'],docs));saved=[]
            for kind in ('sgd','adamw'):
                config={**base,'steps':10,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                model=isolated.run(root,True,source,inputs,config,isolated.review(root,source,inputs,config),uuid.uuid4().hex)
                review=scoring.evaluate(root,benchmark['id'],model['id'],baseline_initialization=True)
                saved.append(results.save(root,benchmark['id'],model['id'],True,review,baseline_initialization=True))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            candidate,baseline=saved[1],saved[0];ids=(candidate['record']['id'],baseline['record']['id'])
            with patch.object(scoring,'evaluate',side_effect=AssertionError('Historical comparison must not execute models.')):
                report=comparisons.compare(root,*ids)
            self.assertEqual(report,comparisons.compare(root,*ids))
            self.assertEqual(report['candidate']['manifest_revision'],candidate['record']['revision'])
            self.assertEqual(report['baseline']['report_revision'],baseline['report']['revision'])
            for section,values in report['comparison']['candidate_minus_baseline'].items():
                for key,value in values.items():
                    a=candidate['report']['metrics'][section][key];b=baseline['report']['metrics'][section][key]
                    self.assertEqual(value,None if a is None or b is None else a-b)
            same=comparisons.compare(root,ids[0],ids[0]);self.assertTrue(all(value==0 for section in same['comparison']['candidate_minus_baseline'].values() for value in section.values() if value is not None))
            for field in ('training_approved','release_approved','language_quality_validated','independent_evaluation_certified'):self.assertFalse(report[field])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
