from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_corpus_document_overlap as audit
from backend.decoder_tokenizer import Tokenizer
from test_decoder_corpus_optimizer import corpus


def window(tokens,offset=0,sha='a'*64,padding=0):
    return {'document_sha256':sha,'offset':offset,'inputs':tokens[:-1]+[0]*padding,
            'targets':tokens[1:]+[0]*padding,'target_mask':[1]*(len(tokens)-1)+[0]*padding}


class DocumentOverlapTest(unittest.TestCase):
    def setUp(self):self.tokenizer=Tokenizer([f'word{i:02d}' for i in range(10)])

    def test_cross_window_span_missed_by_window_audit_is_found(self):
        reference=[window([0,1,2,3,4]),window([4,5,6,7,8],4)]
        result=audit.audit_pair([window([2,3,4,5],sha='b'*64)],reference,self.tokenizer)
        self.assertFalse(result['within_window_overlap_detected']);self.assertTrue(result['additional_document_overlap_detected'])
        self.assertEqual(result['shared_four_token_query_documents'],1);self.assertEqual(result['cross_boundary_shared_query_documents'],1)
        span=result['examples'][0]['shared_span'];self.assertEqual(span['reference_token_offset'],2)
        self.assertTrue(span['reference_crosses_window_boundary']);self.assertFalse(span['query_crosses_window_boundary'])
        self.assertEqual(span['token_ids'],[2,3,4,5])

    def test_boundary_token_padding_and_weighted_copies_do_not_duplicate_documents(self):
        first=window([0,1,2,3,4]);second=window([4,5,6],4,padding=2)
        reconstructed=audit.reconstruct([first,first,second])
        self.assertEqual(len(reconstructed),1);self.assertEqual(reconstructed[0]['tokens'],tuple(range(7)))
        self.assertEqual(reconstructed[0]['boundaries'],{4})

    def test_conflicting_gapped_or_invalid_coordinates_and_shifted_inputs_rejected(self):
        cases=([window([0,1,2,3,4]),window([9,5,6],4)],
               [window([0,1,2,3]),window([5,6,7],5)],
               [window([0,1],4)],[window([0,1],-1)],
               [{**window([0,1,2]),'inputs':[9,9]}])
        for windows in cases:
            with self.assertRaises(ValueError):audit.reconstruct(windows)

    def test_counts_not_truncated_by_example_cap_and_reference_sequences_deduplicated(self):
        query=[window([0,1,2,3,4],sha=f'{i:064x}') for i in range(12)]
        reference=[window([0,1,2,3,4],sha=f'{i+20:064x}') for i in range(3)]
        result=audit.audit_pair(query,reference,self.tokenizer)
        self.assertEqual(result['query_documents'],12);self.assertEqual(result['reference_documents'],3)
        self.assertEqual(result['unique_reference_token_sequences'],1);self.assertEqual(result['exact_duplicate_query_documents'],12)
        self.assertEqual(len(result['examples']),8)

    def test_real_corpus_audit_is_repeatable_and_read_only(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,saved,_=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=audit.audit_corpus(root,saved['id']);self.assertTrue(report['overlap_detected'])
            self.assertEqual(report,audit.audit_corpus(root,saved['id']))
            self.assertEqual(report['training_data_binding']['windows_sha256'],saved['files']['windows.json'])
            for field in ('independent_evaluation_certified','memorization_validated','training_approved','release_approved'):self.assertFalse(report[field])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
