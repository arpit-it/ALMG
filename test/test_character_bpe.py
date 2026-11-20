import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend.decoder_character_bpe import CharacterBPE
from backend import decoder_datasets as datasets,decoder_tokenizer_experiments as experiments
from backend.run_manifest import digest


class CharacterBPETests(unittest.TestCase):
    def test_golden_merges_nfc_roundtrip_and_uncovered_characters_never_refit(self):
        golden=CharacterBPE.fit(['abab','acac'],32)
        self.assertEqual(golden.alphabet,['a','b','c']);self.assertEqual(golden.merges,[[0,1],[0,2]])
        self.assertEqual(golden.encode('abac'),[3,4]);self.assertEqual(golden.decode([3,4]),'abac')
        model=CharacterBPE.fit(['café 世界 café 世界 '*4],64);before=model.artifact()
        self.assertEqual(model.decode(model.encode('cafe\u0301 世界')),'café 世界')
        self.assertEqual(model.uncovered('🙂🙂 café'),2)
        with self.assertRaisesRegex(ValueError,'outside the fitted'):model.encode('🙂 café')
        self.assertEqual(model.artifact(),before)
        self.assertEqual(CharacterBPE.restore(json.loads(json.dumps(before))).encode('café'),model.encode('café'))
        with self.assertRaises(ValueError):model.validate_current_model({'vocab_size':len(model.pieces)})

    def test_invalid_alphabet_merge_cap_and_artifact_reject(self):
        for alphabet,merges,cap in ((['b','a'],[],64),(['a','a'],[],64),(['ab'],[],64),(['a'],[[0,1]],64),(['a'],[],True),(['a'],[],31)):
            with self.assertRaises(ValueError):CharacterBPE(alphabet,merges,'a'*64,cap)
        model=CharacterBPE.fit(['aaaa'],32)
        for tokens in ([],[True],[len(model.pieces)]):
            with self.assertRaises(ValueError):model.decode(tokens)
        artifact=model.artifact();artifact['method']['special_tokens']=0
        with self.assertRaises(ValueError):CharacterBPE.restore(artifact)

    def test_experiment_coverage_excludes_unencodable_records_and_preserves_legacy_byte_artifacts(self):
        documents=[{'name':f'{i}.txt','text':text} for i,text in enumerate(['banana bandana café '*8,'日本語 世界 宇宙 '*8,'नमस्ते दुनिया '*8,'orchard apple harvest '*8,'emoji 🐈 🚀 '*8])]
        with TemporaryDirectory() as root:
            dataset=datasets.prepare(root,documents,True,'utf8_bytes')
            byte=experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':320})
            original=(experiments._folder(root,byte['id'])/'manifest.json').read_bytes()
            character=experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':128,'algorithm':'character_bpe'})
            model=CharacterBPE.restore(json.loads((experiments._folder(root,character['id'])/'tokenizer.json').read_text()))
            rows=[json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset['id']/'documents.jsonl').read_text().splitlines()]
            self.assertEqual(model.training_sha256,digest([row['text'] for row in rows if row['split']=='train']))
            for split in ('train','validation','test'):
                selected=[row for row in rows if row['split']==split];report=character['comparison'][split]
                encodable=[row for row in selected if not model.uncovered(row['text'])]
                self.assertEqual(report['documents_encoded'],len(encodable))
                self.assertEqual(report['uncovered_character_count'],sum(model.uncovered(row['text']) for row in selected))
                self.assertEqual(report['encoded_baseline_byte_tokens'],sum(len(row['text'].encode()) for row in encodable))
                if not encodable:self.assertIsNone(report['bpe_tokens']);self.assertIsNone(report['byte_to_bpe_token_ratio'])
            self.assertTrue(character['comparison']['train']['round_trip_verified'])
            self.assertFalse(character['comparison']['validation']['round_trip_verified'])
            self.assertEqual(experiments.read(root,byte['id']),byte)
            self.assertEqual((experiments._folder(root,byte['id'])/'manifest.json').read_bytes(),original)
            exported=experiments.export(root,character['id'],True,character)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:CharacterBPE.restore(json.loads(archive.read('tokenizer.json')))
            with self.assertRaises(ValueError):experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':128,'algorithm':'unknown'})
