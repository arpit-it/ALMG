import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np

from backend import decoder_recipe as recipe,decoder_bundle as bundles,decoder_dataset_training as training,decoder_trials as trials
from backend import decoder_datasets as datasets,decoder_tokenizer_experiments as experiments,decoder_tokenizer_adoptions as adoptions,recipe_contracts
from backend.decoder_model_tokenizer import ModelTokenizer
from backend.decoder_bpe import ByteBPE
from backend.decoder_special_tokens import SpecialTokenizer


def fixture(root):
    texts=['banana bandana café '*8,'日本語 世界 宇宙 '*8,'नमस्ते दुनिया '*8,'orchard apple harvest '*8,'emoji 🐈 🚀 '*8]
    parent=datasets.prepare(root,[{'name':f'{i}.txt','text':text} for i,text in enumerate(texts)],True,'utf8_bytes')
    exp=experiments.train(root,parent['id'],True,parent,{'algorithm':'byte_level_bpe','vocabulary_cap':320})
    return parent,exp,adoptions.adopt(root,exp['id'],True,exp,parent)


class WideVocabularyTests(unittest.TestCase):
    def test_registered_fresh_initialization_bounds_causality_and_maximum_artifact_roundtrip(self):
        with patch('pathlib.Path.open',side_effect=AssertionError('No pretrained files')):
            model=recipe_contracts.initialize_recipe('decoder_from_scratch',{'vocab_size':512})
        self.assertEqual(model.logits([[0,511]]).shape,(1,2,512))
        np.testing.assert_array_equal(model.logits([[0,1,511]])[:,:2],model.logits([[0,1,2]])[:,:2])
        self.assertEqual(recipe.architecture_version(model.config),2)
        self.assertEqual(recipe.architecture_version({'vocab_size':256}),1)
        self.assertEqual(recipe_contracts.recipe_contract('decoder_from_scratch')['architecture_profiles'][-1]['vocabulary_max'],512)
        for size in (True,3,513):
            with self.assertRaises(ValueError):recipe.Decoder({'vocab_size':size})
        with TemporaryDirectory() as root:
            maximum=recipe.Decoder({'vocab_size':512,'width':64,'context_length':128})
            path=Path(root)/'model.json';maximum.save(path)
            self.assertLessEqual(path.stat().st_size,4*1024*1024)
            restored=recipe.Decoder.load(path)
            np.testing.assert_array_equal(restored.logits([[0,511]]),maximum.logits([[0,511]]))

    def test_320_id_dataset_bundle_checkpoint_profile_and_legacy_profile_are_distinct(self):
        from backend import decoder_checkpoint
        with TemporaryDirectory() as root:
            parent,exp,child=fixture(root)
            _,tok,rows,_=training.preflight(root,child)
            self.assertEqual(len(tok.vocabulary),320)
            spec=trials.specification(child);self.assertEqual(spec['recipe_contract']['pipeline']['stages']['architecture']['version'],2)
            model=recipe.Decoder({'vocab_size':320});path=Path(root)/'bundle'
            manifest=bundles.save(path,model,tok,{'seed':7},'pretraining_local')
            self.assertEqual(manifest['stages']['architecture'],2)
            self.assertEqual(bundles.load(path)[1].artifact(),tok.artifact())
            expected=decoder_checkpoint.revision(model.config,tok,[r['text'] for r in rows if r['split']=='train'])
            decoder_checkpoint.save(Path(root)/'checkpoint',model,tok,expected,50,'pretraining_local')
            self.assertEqual(decoder_checkpoint.load(Path(root)/'checkpoint',expected)[1].fingerprint(),tok.fingerprint())
            manifest['stages']['architecture']=1;(path/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'architecture version'):bundles.load(path)
            legacy=bundles.save(Path(root)/'legacy',recipe.Decoder({'vocab_size':256}),datasets.Tokenizer.restore(json.loads((Path(root)/'decoder-datasets'/parent['id']/'tokenizer.json').read_text())),{'seed':7})
            self.assertEqual(legacy['stages']['architecture'],1);bundles.load(Path(root)/'legacy')

    def test_byte_control_preview_replacement_keeps_bounds_controls_and_lossless_input(self):
        base=ByteBPE.fit(['hello world'],256)
        codec=SpecialTokenizer(base,{'pad':'<PAD>','bos':'<BOS>','eos':'<EOS>','unk':'<UNK>'})
        selected={'parent_dataset_id':'a'*32,'experiment_id':'b'*32,'parent_manifest_sha256':'c'*64,'experiment_revision':'d'*64,'approval_sha256':'e'*64}
        tok=ModelTokenizer(codec.artifact(),selected)
        with self.assertRaises(UnicodeDecodeError):codec.decode([255])
        self.assertEqual(tok.decode([codec.special_ids['bos'],255,codec.special_ids['unk'],codec.special_ids['eos']]),'�<UNK>')
        self.assertEqual(tok.decode([0xe2,codec.special_ids['pad'],0x82,0xac]),'€')
        self.assertEqual(tok.decode(tok.encode('café 世界 🚀')),'café 世界 🚀')
        with self.assertRaises(ValueError):tok.decode([len(tok.vocabulary)])
        with self.assertRaises(ValueError):base.decode([255],errors='ignore')
        with self.assertRaises(ValueError):tok.decode([255]*4101)

    def test_wide_generated_preview_has_separate_explicit_bounds_from_dataset_decode(self):
        base=ByteBPE.fit(['ab '*1024],272)
        selected={'parent_dataset_id':'a'*32,'experiment_id':'b'*32,'parent_manifest_sha256':'c'*64,'experiment_revision':'d'*64,'approval_sha256':'e'*64}
        tok=ModelTokenizer(base.artifact(),selected)
        largest=max(range(len(base.pieces)),key=lambda i:len(base.pieces[i]))
        with self.assertRaises(ValueError):tok.decode([largest]*12)
        self.assertGreater(len(tok.decode_preview([largest]*12).encode()),4096)
        self.assertIn('65536',tok.artifact()['generated_byte_decode'])
        self.assertEqual(ModelTokenizer.restore(tok.artifact()).artifact(),tok.artifact())
        with self.assertRaises(ValueError):tok.decode_preview([largest]*160)
        with self.assertRaises(ValueError):tok.decode_preview([0]*161)
        invalid=ByteBPE([[255,255]]+[[i,i] for i in range(256,267)],'f'*64,272)
        imported=ModelTokenizer(invalid.artifact(),selected)
        with self.assertRaisesRegex(ValueError,'UTF-8 output bytes'):imported.decode_preview([267]*16)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Actual local Metal execution')
    def test_real_320_id_metal_trial_persists_architecture_profile_two(self):
        with TemporaryDirectory() as root:
            parent,exp,child=fixture(root)
            result=training.run(recipe_contracts.initialize_recipe,root,child,Path(root)/'artifacts')
            model,tok,manifest=bundles.load(Path(root)/'artifacts'/'bundle')
            self.assertEqual(manifest['stages']['architecture'],2)
            self.assertEqual(model.config['vocab_size'],320)
            self.assertEqual(manifest['training']['steps'],100)
            self.assertLess(result['cpu_inference_max_error'],1e-5)
            self.assertTrue(all(np.isfinite(value).all() for value in model.parameters.values()))
