from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
import numpy as np
from backend import decoder_corpus_benchmarks as benchmarks, decoder_corpus_benchmark_evaluation as scoring, decoder_corpus_benchmark_results as results
from backend import decoder_corpus_optimizer as training, decoder_corpus_inputs as inputs, decoder_datasets as datasets, decoder_licenses as licenses
from backend import decoder_architecture_plans as plans, decoder_architecture_initializations as initializations
from backend.run_manifest import digest,file_digest
from test_decoder_corpus_benchmarks import documents
from test_decoder_corpus_optimizer import corpus


def legacy(root,review,docs,tokenizer):
    review=deepcopy(review);review['format']='almg-corpus-benchmark-review-v1';review['schema_version']=1
    review.pop('document_overlap_checks',None);review.pop('document_overlap_protocol_revision',None)
    review['blockers']=[value for value in review['blockers'] if not value.startswith('Benchmark documents overlap')];review['compatible']=not review['blockers']
    review['revision']=digest({k:v for k,v in review.items() if k!='revision'})
    identifier=uuid.uuid4().hex;folder=root/'decoder-corpus-benchmarks'/identifier;folder.mkdir(parents=True)
    _,windows,_=benchmarks._prepare(docs,tokenizer,review['sequence_length'])
    for name,value in (('documents.json',docs),('windows.json',windows),('tokenizer.json',tokenizer.artifact())):(folder/name).write_text(json.dumps(value))
    record={'format':'almg-saved-corpus-benchmark-v1','schema_version':1,'id':identifier,'review':review,
            'files':{name:file_digest(folder/name) for name in ('documents.json','windows.json','tokenizer.json')}}
    record['revision']=digest(record);(folder/'record.json').write_text(json.dumps(record));return record


class DocumentAdmissionTest(unittest.TestCase):
    def test_v2_preparation_preserves_safe_legacy_inputs_and_rejects_old_reviews(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,_=corpus(root);docs=documents();review=benchmarks.review(root,saved['id'],docs)
            self.assertEqual(review['schema_version'],2);self.assertTrue(review['compatible'])
            tokenizer=training._source(root,source,saved)[4];old=legacy(root,review,docs,tokenizer)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(benchmarks.read(root,old['id']),old)
            with self.assertRaises(ValueError):benchmarks.save(root,saved['id'],True,docs,old['review'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            current=benchmarks.save(root,saved['id'],True,docs,review);self.assertEqual(current['schema_version'],2)
            self.assertEqual(benchmarks.read(root,current['id']),current)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def test_cross_window_overlap_blocks_new_save_and_legacy_scoring_before_forward(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);rng=np.random.default_rng(7);words=[f'word{i:02d}' for i in range(12)]
            dataset=datasets.prepare(root,[{'name':f'local-{i}.txt','text':' '.join(rng.permutation(words).tolist())} for i in range(6)],True)
            for item in dataset['sources']:dataset=licenses.declare(root,dataset['id'],True,dataset,item['source_sha256'],'user_created','Local boundary test fixture.')
            plan=plans.save(root,True,plans.review({**plans.DEFAULT,'vocab_size':12}));source=initializations.run(root,plan['id'],True,plan)
            corpus_record=inputs.save(root,plan['id'],True,source,dataset,8,inputs.review(root,plan['id'],source,dataset,8))
            _,_,_,existing,tokenizer=training._source(root,source,corpus_record);rows=[json.loads(line) for line in (root/'decoder-datasets'/dataset['id']/'documents.jsonl').read_text().splitlines()]
            chosen=None
            for row in rows:
                if row['split']!='train':continue
                for offset in (6,7):
                    docs=documents();docs[0]['text']=tokenizer.decode(tokenizer.encode(row['text'])[offset:offset+4]);review=benchmarks.review(root,corpus_record['id'],docs)
                    if not any(item['overlap_detected'] for item in review['overlap_checks'].values()) and review['document_overlap_checks']['train']['overlap_detected']:
                        chosen=(docs,review);break
                if chosen:break
            self.assertIsNotNone(chosen);docs,review=chosen;self.assertFalse(review['compatible'])
            with self.assertRaises(ValueError):benchmarks.save(root,corpus_record['id'],True,docs,review)
            old=legacy(root,review,docs,tokenizer);self.assertEqual(benchmarks.read(root,old['id']),old)
            class Model:
                def logits(self,*args):raise AssertionError('Admission must block before scoring.')
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(scoring.heldout,'evaluation_context',return_value=(Model(),existing,tokenizer,{},corpus_record)),self.assertRaisesRegex(ValueError,'Document-level overlap'):
                scoring.evaluate(root,old['id'],'a'*32)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_v2_saved_score_requires_clear_document_findings(self):
        # A recomputed digest must not turn a positive finding into admitted evidence.
        report={'format':'almg-corpus-benchmark-evaluation-v2','schema_version':2,'protocol':{'schema_version':2,'document_overlap_protocol_revision':'a'*64},
                'source':{'record_id':'b'*32,'record_revision':'c'*64,'model_sha256':'d'*64},
                'benchmark_binding':{'id':'e'*32,'revision':'f'*64,'review_revision':'1'*64},
                'current_overlap_checks':{key:{'overlap_detected':False} for key in ('train','validation','test')},
                'current_document_overlap_checks':{key:{'overlap_detected':False} for key in ('train','validation','test')},
                'training_approved':False,'release_approved':False,'language_quality_validated':False,'independent_evaluation_certified':False}
        report['protocol_revision']=digest(report['protocol']);report['revision']=digest(report);results._validate(report)
        report['current_document_overlap_checks']['train']['overlap_detected']=True;report['revision']=digest({k:v for k,v in report.items() if k!='revision'})
        with self.assertRaises(ValueError):results._validate(report)
