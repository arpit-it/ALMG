import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend.decoder_bpe import ByteBPE
from backend.decoder_unigram import UnigramTokenizer
from backend.decoder_special_tokens import SpecialTokenizer,definitions
from backend import decoder_tokenizer_experiments as experiments,decoder_datasets as datasets

LABELS={'pad':'<PAD>','bos':'<BOS>','eos':'<EOS>','unk':'<UNK>'}


class SpecialTokenizerTests(unittest.TestCase):
    def test_reserved_ids_boundaries_literal_markers_and_reload(self):
        base=ByteBPE.fit(['banana bandana '*4],268);model=SpecialTokenizer(base,LABELS)
        self.assertEqual(list(model.special_ids.values()),list(range(len(base.pieces),len(base.pieces)+4)))
        text='literal <EOS> café 🚀';ids=model.encode(text)
        self.assertEqual(ids[0],model.special_ids['bos']);self.assertEqual(ids[-1],model.special_ids['eos'])
        self.assertEqual(ids.count(model.special_ids['eos']),1);self.assertNotIn(model.special_ids['pad'],ids)
        self.assertEqual(model.decode(ids),text);self.assertEqual(model.decode(ids,skip_special_tokens=False),'<BOS>'+text+'<EOS>')
        self.assertEqual(model.encode(text,add_boundaries=False),base.encode(text))
        euro=base.encode('€')
        self.assertEqual(model.decode(euro[:1]+[model.special_ids['pad']]+euro[1:]),'€')
        restored=SpecialTokenizer.restore(json.loads(json.dumps(model.artifact())));self.assertEqual(restored.encode(text),ids)
        with self.assertRaises(ValueError):model.validate_current_model({'vocab_size':len(model.pieces)})

    def test_unknown_replacement_is_explicit_and_never_refits(self):
        base=UnigramTokenizer.fit(['abab abab '*4],64);before=base.artifact()
        reject=SpecialTokenizer(base,LABELS,'reject')
        with self.assertRaises(ValueError):reject.encode('ab ΩΩ')
        replace=SpecialTokenizer(base,LABELS,'replace');ids=replace.encode('ab ΩΩ')
        self.assertEqual(ids.count(replace.special_ids['unk']),2)
        self.assertEqual(replace.decode(ids),'ab <UNK><UNK>');self.assertEqual(base.artifact(),before)
        self.assertEqual(replace.decode([replace.special_ids['unk']]),'<UNK>')

    def test_invalid_labels_policies_nested_wrappers_and_id_tampering_reject(self):
        base=ByteBPE.fit(['sample sample'],256)
        for labels in ({'bad':'<X>'},{'bos':'<X>','eos':'<X>'},{'bos':'white space'},{'bos':'<Ω>'}):
            with self.assertRaises(ValueError):definitions(labels)
        with self.assertRaises(ValueError):SpecialTokenizer(base,{'bos':'<B>'},'replace')
        model=SpecialTokenizer(base,{'bos':'<START>','eos':'<END>'})
        self.assertEqual(model.decode(model.encode('sample'),skip_special_tokens=False),'<START>sample<END>')
        with self.assertRaises(ValueError):SpecialTokenizer(model,LABELS)
        artifact=model.artifact();artifact['special_ids']['bos']=0
        with self.assertRaises(ValueError):SpecialTokenizer.restore(artifact)

    def test_experiment_total_cap_lossy_accounting_export_and_legacy_compatibility(self):
        docs=[{'name':f'{i}.txt','text':text} for i,text in enumerate(['banana bandana café '*8,'日本語 世界 宇宙 '*8,'नमस्ते दुनिया '*8,'orchard apple harvest '*8,'emoji 🐈 🚀 '*8])]
        with TemporaryDirectory() as root:
            dataset=datasets.prepare(root,docs,True,'utf8_bytes');legacy=experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':320})
            with self.assertRaises(ValueError):experiments.train(root,dataset['id'],True,dataset,{'vocabulary_cap':256,'special_tokens':LABELS})
            config={'algorithm':'unigram','vocabulary_cap':128,'special_tokens':LABELS,'unknown_policy':'replace'}
            record=experiments.train(root,dataset['id'],True,dataset,config)
            model=SpecialTokenizer.restore(json.loads((experiments._folder(root,record['id'])/'tokenizer.json').read_text()))
            self.assertEqual(model.vocabulary_size,128);self.assertLessEqual(len(model.pieces),128)
            self.assertEqual(record['comparison']['train']['boundary_tokens'],6)
            for split in ('validation','test'):
                report=record['comparison'][split];self.assertEqual(report['documents_encoded'],1)
                self.assertEqual(report['documents_lossless'],0);self.assertEqual(report['documents_lossy'],1)
                self.assertEqual(report['unknown_tokens'],report['uncovered_character_count'])
                self.assertIsNone(report['byte_to_token_ratio']);self.assertIsNone(report['lossless_token_count'])
                self.assertFalse(report['round_trip_verified'])
            self.assertEqual(experiments.read(root,legacy['id']),legacy);self.assertEqual(experiments.read(root,record['id']),record)
            exported=experiments.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:SpecialTokenizer.restore(json.loads(archive.read('tokenizer.json')))
            self.assertFalse(record['model_training_enabled']);self.assertFalse((Path(root)/'decoder-trials').exists())
