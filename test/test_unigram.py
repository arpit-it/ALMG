import base64
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend.decoder_unigram import UnigramTokenizer
from backend import decoder_datasets as datasets,decoder_tokenizer_experiments as experiments
from backend.run_manifest import digest


class UnigramTests(unittest.TestCase):
    def test_forward_backward_matches_enumerated_segmentations_and_viterbi(self):
        model=UnigramTokenizer(['a','b'],['a','b','ab'],[.25,.25,.5],'a'*64,32)
        likelihood,counts=model._expected('ab')
        self.assertAlmostEqual(likelihood,math.log(.25*.25+.5))
        self.assertAlmostEqual(counts[0],1/9);self.assertAlmostEqual(counts[1],1/9);self.assertAlmostEqual(counts[2],8/9)
        self.assertEqual(model.encode('ab'),[2]);self.assertEqual(model.encode('aba'),[2,0])
        self.assertEqual(model.decode([2,0]),'aba')
        self.assertEqual(UnigramTokenizer.restore(model.artifact()).encode('ab'),[2])

    def test_em_likelihood_normalization_determinism_unicode_and_unknown_rejection(self):
        texts=['café 世界 café 世界 '*4,'नमस्ते नमस्ते '*4]
        model=UnigramTokenizer.fit(texts,128)
        self.assertEqual(model.artifact(),UnigramTokenizer.fit(texts,128).artifact())
        self.assertEqual(len(model.history),6);self.assertAlmostEqual(sum(model.probabilities),1)
        self.assertTrue(all(right>=left-1e-6 for left,right in zip(model.history,model.history[1:])))
        self.assertEqual(model.decode(model.encode('cafe\u0301 世界')),'café 世界')
        before=model.artifact()
        with self.assertRaises(ValueError):model.encode('🚀')
        self.assertEqual(model.artifact(),before)
        self.assertFalse(model.artifact()['method']['cross_word_pieces'])
        with self.assertRaises(ValueError):model.validate_current_model({'vocab_size':len(model.pieces)})

    def test_invalid_probabilities_vocabulary_and_method_reject(self):
        for probabilities in ([.5,.6],[0.,1.],[float('nan'),.5],[True,False]):
            with self.assertRaises(ValueError):UnigramTokenizer(['a','b'],['a','b'],probabilities,'a'*64,32)
        with self.assertRaises(ValueError):UnigramTokenizer(['a'],['a','a a'],[.5,.5],'a'*64,32)
        artifact=UnigramTokenizer.fit(['abababab'],32).artifact();artifact['method']['em_updates']=4
        with self.assertRaises(ValueError):UnigramTokenizer.restore(artifact)

    def test_approved_experiment_fit_only_training_export_reload_and_coverage(self):
        docs=[{'name':f'{index}.txt','text':text} for index,text in enumerate(['banana bandana café '*8,'日本語 世界 宇宙 '*8,'नमस्ते दुनिया '*8,'orchard apple harvest '*8,'emoji 🐈 🚀 '*8])]
        with TemporaryDirectory() as root:
            dataset=datasets.prepare(root,docs,True,'utf8_bytes')
            record=experiments.train(root,dataset['id'],True,dataset,{'algorithm':'unigram','vocabulary_cap':128})
            artifact=json.loads((experiments._folder(root,record['id'])/'tokenizer.json').read_text());model=UnigramTokenizer.restore(artifact)
            rows=[json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset['id']/'documents.jsonl').read_text().splitlines()]
            self.assertEqual(model.training_sha256,digest([row['text'] for row in rows if row['split']=='train']))
            self.assertTrue(record['comparison']['train']['round_trip_verified']);self.assertFalse(record['comparison']['validation']['round_trip_verified'])
            self.assertIsNone(record['comparison']['validation']['byte_to_token_ratio'])
            self.assertEqual(experiments.read(root,record['id']),record)
            exported=experiments.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:UnigramTokenizer.restore(json.loads(archive.read('tokenizer.json')))
            self.assertFalse(record['model_training_enabled']);self.assertFalse((Path(root)/'decoder-trials').exists())
