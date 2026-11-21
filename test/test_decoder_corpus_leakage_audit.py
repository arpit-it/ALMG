from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_corpus_leakage_audit as audit
from backend.decoder_tokenizer import Tokenizer
from test_decoder_corpus_optimizer import corpus


def window(tokens, padding=0, fill=0):
    return {'inputs':tokens[:-1]+[fill]*padding,'targets':tokens[1:]+[fill]*padding,
            'target_mask':[1]*(len(tokens)-1)+[0]*padding,'document_sha256':'local','offset':0}


class LeakageAuditTest(unittest.TestCase):
    def setUp(self):self.tokenizer=Tokenizer(['a','b','c','d'])

    def test_padding_excluded_real_zero_preserved_and_reference_copies_deduplicated(self):
        query=window([1,0,2],2,3);reference=window([1,0,2],2,1)
        result=audit.audit_pair([query],[reference,deepcopy(reference)],self.tokenizer)
        self.assertEqual(result['exact_duplicate_query_windows'],1)
        self.assertEqual(result['shared_four_token_query_windows'],0)
        self.assertEqual(result['query_windows_shorter_than_four_tokens'],1)
        self.assertEqual(result['reference_windows_including_mixing_copies'],2)
        self.assertEqual(result['unique_reference_token_sequences'],1)
        self.assertIsNone(result['examples'][0]['shared_span'])
        self.assertTrue(result['overlap_detected'])
        changed=audit.audit_pair([window([1,2])],[window([1,0,2])],self.tokenizer)
        self.assertFalse(changed['overlap_detected'])

    def test_shifted_four_token_span_provenance_and_exact_window_are_distinct(self):
        query=window([0,1,2,3,0]);reference=window([3,0,1,2,3,1]);reference['offset']=8
        result=audit.audit_pair([query],[reference],self.tokenizer)
        self.assertEqual(result['exact_duplicate_query_windows'],0)
        self.assertEqual(result['shared_four_token_query_windows'],1)
        self.assertEqual(result['shared_four_token_window_pairs'],1)
        example=result['examples'][0];self.assertEqual(example['reference_window_document_offset'],8)
        self.assertEqual(example['shared_span'],{'query_token_offset':0,'reference_token_offset':1,'token_ids':[0,1,2,3],'text':'a b c d'})

    def test_no_cross_window_matching_and_examples_are_bounded_without_truncating_counts(self):
        result=audit.audit_pair([window([0,1,2,3])],[window([0,1,2]),window([2,3])],self.tokenizer)
        self.assertFalse(result['overlap_detected'])
        row=window([0,1,2,3]);result=audit.audit_pair([row]*12,[row],self.tokenizer)
        self.assertEqual(result['exact_duplicate_query_windows'],12)
        self.assertEqual(result['shared_four_token_window_pairs'],12)
        self.assertEqual(len(result['examples']),8)
        self.assertEqual([r['query_window_index'] for r in result['examples']],list(range(8)))

    def test_invalid_masks_rejected(self):
        for mask in ([0,0],[0,1],[1,0,1]):
            row={'inputs':[0]*len(mask),'targets':[0]*len(mask),'target_mask':mask}
            with self.assertRaises(ValueError):audit.active_tokens(row)

    def test_real_snapshot_provenance_repeats_and_tamper_rejection_without_writes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,saved,_=corpus(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=audit.audit(root,saved['id'])
            self.assertEqual(report['corpus_revision'],saved['revision'])
            self.assertEqual(report['evaluation_data_binding']['windows_sha256'],saved['files']['windows.json'])
            self.assertEqual(set(report['comparisons']),{'validation_against_train','test_against_train','test_against_validation'})
            self.assertTrue(report['overlap_detected']);self.assertTrue(report['requires_overlap_review'])
            for field in ('independent_evaluation_certified','memorization_validated','training_approved','release_approved'):self.assertFalse(report[field])
            self.assertEqual(report,audit.audit(root,saved['id']))
            report['protocol']['comparisons'][0].append('changed')
            self.assertEqual(audit.audit(root,saved['id'])['protocol']['comparisons'][0],['validation','train'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            path=root/'decoder-corpus-inputs'/saved['id']/'windows.json';original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):audit.audit(root,saved['id'])
            finally:path.write_bytes(original)
            with self.assertRaises(ValueError):audit.audit(root,'invalid-id')
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
