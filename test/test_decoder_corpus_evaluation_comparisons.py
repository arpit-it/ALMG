from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_evaluation_comparisons as comparisons, decoder_corpus_evaluations as saved, decoder_corpus_isolated as isolated
from backend.run_manifest import digest
from test_decoder_corpus_optimizer import corpus


def report():
    return {'evaluation_data_binding':{'windows':'same'},
            'heldout':{'protocol_revision':'one','implementation_sha256':'same','runtime':{},
                'metrics':{split:{'window_count':1,'target_tokens':1,'dense_positions':1,'padding_positions':0,
                    'cross_entropy_nats_per_target':1.,'perplexity':None,'teacher_forced_token_accuracy':1.,'failure_examples':[]} for split in ('validation','test')}},
            'generation':{'protocol_revision':'one','implementation_sha256':'same','runtime':{},
                'metrics':{split:{'window_count':1,'reference_target_tokens':1,'generated_tokens':1,'generated_transitions':0,
                    'exact_continuation_match_rate':1.,'free_running_reference_token_match_rate':1.,'adjacent_repeat_rate':None,'examples':[]} for split in ('validation','test')}},
            'overlap':{'protocol_revision':'one','implementation_sha256':'same'}}


class SavedEvaluationComparisonTest(unittest.TestCase):
    def test_signed_deltas_and_unavailable_metrics_without_coercing_invalid_values(self):
        self.assertEqual(comparisons._delta(1.,2.),-1.)
        self.assertIsNone(comparisons._delta(None,2.,nullable=True))
        self.assertIsNone(comparisons._delta(None,None,nullable=True))
        for value in (True,-1.,float('nan'),float('inf'),'1',None):
            with self.assertRaises(ValueError):comparisons._delta(value,1.)
        with self.assertRaises(ValueError):comparisons._delta(1.1,.5,maximum=1)
        with self.assertRaises(ValueError):comparisons._delta(None,'bad',nullable=True)

    def test_protocol_producer_runtime_and_data_mismatches_rejected(self):
        original=report();other=deepcopy(original);other['evaluation_data_binding']={}
        with self.assertRaises(ValueError):comparisons._compare_reports(original,other)
        for section in ('heldout','generation','overlap'):
            for field in ('protocol_revision','implementation_sha256'):
                other=deepcopy(original);other[section][field]='changed'
                with self.assertRaises(ValueError):comparisons._compare_reports(original,other)
            if section!='overlap':
                other=deepcopy(original);other[section]['runtime']={'numpy':'changed'}
                with self.assertRaises(ValueError):comparisons._compare_reports(original,other)

    def test_coverage_mismatch_rejected_and_null_self_differences_retained(self):
        original=report();loss,generation,examples=comparisons._compare_reports(original,deepcopy(original))
        self.assertEqual(loss['test']['cross_entropy_nats_per_target'],0.)
        self.assertIsNone(loss['test']['perplexity']);self.assertIsNone(generation['test']['adjacent_repeat_rate'])
        for section,key in (('heldout','target_tokens'),('generation','generated_tokens')):
            other=deepcopy(original);other[section]['metrics']['test'][key]+=1
            with self.assertRaises(ValueError):comparisons._compare_reports(original,other)

    def test_invalid_snapshot_ids_do_not_write(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):comparisons.compare(root,'invalid','a'*32)
            self.assertEqual(list(root.iterdir()),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires real completed models and stored snapshots')
    def test_real_saved_comparison_is_historical_read_only_and_deterministic(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,inputs,base=corpus(root);snapshots=[]
            for kind in ('sgd','adamw'):
                config={**base,'steps':10,'optimizer':kind,'weight_decay':.01 if kind=='adamw' else 0.}
                model=isolated.run(root,True,source,inputs,config,isolated.review(root,source,inputs,config),uuid.uuid4().hex)
                snapshots.append(saved.save(root,model['id'],True,saved.review(root,model['id'])))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            candidate,baseline=snapshots[1],snapshots[0];ids=(candidate['record']['id'],baseline['record']['id'])
            with patch.object(saved,'review',side_effect=AssertionError('Do not recompute historical metrics.')):
                result=comparisons.compare(root,*ids)
            self.assertEqual(result,comparisons.compare(root,*ids))
            for split in ('validation','test'):
                expected=candidate['report']['heldout']['metrics'][split]['cross_entropy_nats_per_target']-baseline['report']['heldout']['metrics'][split]['cross_entropy_nats_per_target']
                self.assertEqual(result['candidate_minus_baseline']['heldout'][split]['cross_entropy_nats_per_target'],expected)
            self.assertEqual(result['candidate']['manifest_revision'],candidate['record']['revision'])
            self.assertEqual(result['baseline']['report_revision'],baseline['report']['revision'])
            self.assertEqual(result['revision'],digest({k:v for k,v in result.items() if k!='revision'}))
            for field in ('training_approved','release_approved','language_quality_validated'):self.assertFalse(result[field])
            same=comparisons.compare(root,ids[0],ids[0])
            self.assertTrue(all(value==0 for section in same['candidate_minus_baseline'].values() for split in section.values() for value in split.values() if value is not None))
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
