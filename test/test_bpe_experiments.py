import base64
import importlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import unicodedata
import zipfile
from backend.decoder_bpe import ByteBPE
from backend.decoder_tokenizer import Tokenizer
from backend import decoder_tokenizer_experiments as experiments,decoder_datasets as datasets
from backend.run_manifest import digest


class ByteBPETests(unittest.TestCase):
    def test_deterministic_training_compression_multilingual_roundtrip_and_reload(self):
        golden=ByteBPE.fit(['abab','acac'],272)
        self.assertEqual(golden.merges,[[97,98],[97,99]])
        self.assertEqual(golden.encode('abac'),[256,257])
        self.assertTrue(all(token<256 for token in golden.encode('🙂🙂')))
        training=['banana bandana banana bandana café '*8,'नमस्ते 世界 🐈 café '*4]
        model=ByteBPE.fit(training,320);self.assertEqual(model.artifact(),ByteBPE.fit(training,320).artifact())
        self.assertGreater(len(model.pieces),256);self.assertLessEqual(len(model.pieces),320)
        self.assertLess(len(model.encode(training[0])),len(training[0].encode()))
        restored=ByteBPE.restore(json.loads(json.dumps(model.artifact())))
        for text in training+['unseen Ω 日本語 🚀','cafe\u0301\tline\nnext']:
            ids=restored.encode(text);self.assertEqual(restored.decode(ids),unicodedata.normalize('NFC',text))
        self.assertEqual(model.training_sha256,digest([unicodedata.normalize('NFC',text) for text in training]))
        with self.assertRaises(ValueError):model.validate_current_model({'vocab_size':len(model.pieces)})
        with self.assertRaises(ValueError):model.validate_current_model({'vocab_size':256})
        with self.assertRaises(ValueError):Tokenizer.restore(model.artifact())

    def test_invalid_config_merges_and_tokens_fail(self):
        for cap in (True,255,513):
            with self.assertRaises(ValueError):ByteBPE.fit(['sample text'],cap)
        for merges in ([[[256,0]]],[[0,256]],[[0,1],[0,1]],[[True,1]]):
            with self.assertRaises(ValueError):ByteBPE(merges,'a'*64,320)
        model=ByteBPE.fit(['banana banana'],272)
        for ids in ([],[True],[-1],[len(model.pieces)]):
            with self.assertRaises(ValueError):model.decode(ids)
        with self.assertRaises(ValueError):model.encode('x'*4097)
        artifact=model.artifact();artifact['method']['version']=True
        with self.assertRaises(ValueError):ByteBPE.restore(artifact)

    def test_experiment_uses_only_training_split_preserves_dataset_exports_and_recovers(self):
        docs=[{'name':f'{i}.txt','text':text} for i,text in enumerate([
            'banana bandana café '*8,'日本語 世界 宇宙 '*8,'नमस्ते दुनिया '*8,'orchard apple harvest '*8,'emoji 🐈 🚀 '*8])]
        with TemporaryDirectory() as root:
            dataset=datasets.prepare(root,docs,True,'utf8_bytes');folder=Path(root)/'decoder-datasets'/dataset['id'];before={p.name:p.read_bytes() for p in folder.iterdir()}
            with self.assertRaises(ValueError):experiments.train(root,dataset['id'],False,dataset,{'vocabulary_cap':320})
            with self.assertRaises(ValueError):experiments.train(root,dataset['id'],True,{}, {'vocabulary_cap':320})
            with self.assertRaises(ValueError):experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':320,'special_tokens':['x']})
            record=experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':320})
            rows=[json.loads(line) for line in (folder/'documents.jsonl').read_text().splitlines()]
            training=[row['text'] for row in rows if row['split']=='train']
            self.assertEqual(record['training_documents_sha256'],digest(training))
            importlib.reload(experiments);self.assertEqual(experiments.read(root,record['id']),record)
            self.assertEqual(experiments.list_experiments(root,dataset['id']),[record])
            self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
            exported=experiments.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:
                self.assertEqual(set(archive.namelist()),{'manifest.json','tokenizer.json'})
                self.assertEqual(json.loads(archive.read('manifest.json')),record)
                ByteBPE.restore(json.loads(archive.read('tokenizer.json')))
            self.assertFalse(record['model_training_enabled']);self.assertFalse((Path(root)/'decoder-trials').exists())
            path=Path(root)/'decoder-tokenizer-experiments'/record['id']/'tokenizer.json';path.write_text('{}')
            with self.assertRaises(ValueError):experiments.read(root,record['id'])
