from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_corpus_benchmarks as benchmarks
from backend.decoder_tokenizer import Tokenizer
from test_decoder_corpus_optimizer import corpus


def documents():
    return [{'name':'independent-local.txt','text':'amber amber birch birch cedar cedar dune dune',
             'license_basis':'user_created','permission_note':'Local evaluation-only fixture.',
             'independent_evaluation_only':True}]


class CorpusBenchmarkTest(unittest.TestCase):
    def test_fixed_tokenizer_masks_duplicates_and_input_bounds(self):
        tokenizer=Tokenizer(['amber','birch','cedar','dune']);before=tokenizer.artifact()
        sources,windows,blockers=benchmarks._prepare(documents(),tokenizer,8)
        self.assertEqual(before,tokenizer.artifact());self.assertEqual(blockers,[])
        self.assertEqual(sum(windows[0]['target_mask']),7);self.assertEqual(windows[0]['target_mask'][-1],0)
        self.assertEqual(sources[0]['token_count'],8)
        for changes in ({'text':'unknown word'},{'text':'amber'},{'name':' '},{'independent_evaluation_only':1}):
            changed=documents();changed[0].update(changes)
            with self.assertRaises(ValueError):benchmarks._prepare(changed,tokenizer,8)
        duplicate=documents()+documents();duplicate[1]['name']='other.txt'
        with self.assertRaises(ValueError):benchmarks._prepare(duplicate,tokenizer,8)
        many=documents();many[0]['text']=' '.join(['amber']*300)
        with self.assertRaises(ValueError):benchmarks._prepare(many,tokenizer,8)
        self.assertEqual(before,tokenizer.artifact())

    def test_permissions_and_evaluation_only_declarations_remain_blockers(self):
        tokenizer=Tokenizer(['amber','birch','cedar','dune']);changed=documents()
        changed[0].update(license_basis='needs_review',permission_note='',independent_evaluation_only=False)
        _,_,blockers=benchmarks._prepare(changed,tokenizer,8);self.assertEqual(len(blockers),2)

    def test_real_corpus_overlap_review_and_confirmation_fail_before_writes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,saved,_=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            docs=documents();docs[0]['text']='amber birch cedar dune amber birch cedar dune'
            review=benchmarks.review(root,saved['id'],docs)
            self.assertFalse(review['compatible']);self.assertTrue(review['blockers'])
            self.assertTrue(any(item['overlap_detected'] for item in review['overlap_checks'].values()))
            with self.assertRaises(ValueError):benchmarks.save(root,saved['id'],True,docs,review)
            with self.assertRaises(ValueError):benchmarks.save(root,saved['id'],False,documents(),{})
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_real_confirmed_snapshot_reloads_and_preserves_original_corpus(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,saved,_=corpus(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            docs=documents();review=benchmarks.review(root,saved['id'],docs)
            self.assertTrue(review['compatible']);self.assertEqual(review,benchmarks.review(root,saved['id'],docs))
            self.assertFalse(review['tokenizer_refitted']);self.assertFalse(review['independent_evaluation_certified'])
            changed=deepcopy(docs);changed[0]['permission_note']='Changed permission note.'
            with self.assertRaises(ValueError):benchmarks.save(root,saved['id'],True,changed,review)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            result=benchmarks.save(root,saved['id'],True,docs,review)
            self.assertEqual(result,benchmarks.read(root,result['id']))
            self.assertEqual(result['review']['training_data_binding']['windows_sha256'],saved['files']['windows.json'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            folder=root/'decoder-corpus-benchmarks'/result['id']
            self.assertEqual(json.loads((folder/'documents.json').read_text()),docs)
            self.assertEqual(json.loads((folder/'tokenizer.json').read_text()),json.loads((root/'decoder-corpus-inputs'/saved['id']/'tokenizer.json').read_text()))
            path=folder/'windows.json';original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):benchmarks.read(root,result['id'])
            finally:path.write_bytes(original)
            self.assertEqual(result,benchmarks.read(root,result['id']))

    def test_invalid_benchmark_ids_rejected_without_writes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for identifier in (None,'invalid',3):
                with self.assertRaises(ValueError):benchmarks.read(root,identifier)
            self.assertEqual(list(root.iterdir()),[])
