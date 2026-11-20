import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import decoder_tokenizer_adoptions as adoptions, decoder_tokenizer_experiments as experiments
from backend import decoder_datasets as datasets, decoder_dataset_training as training
from backend import decoder_bundle as bundles, decoder_checkpoint as checkpoints, decoder_trials as trials, decoder_licenses
from backend.decoder_model_tokenizer import ModelTokenizer, FORMAT
from backend.decoder_tokenizer import Tokenizer
from backend.decoder_bpe import ByteBPE
from backend.decoder_recipe import Decoder
from backend.run_manifest import digest, file_digest


def fixture(root, algorithm='character_bpe', cap=128, special=True, multilingual=False):
    texts = (['banana bandana café '*8, '日本語 世界 宇宙 '*8, 'नमस्ते दुनिया '*8,
              'orchard apple harvest '*8, 'emoji 🐈 🚀 '*8] if multilingual else
             ['abcdefghijklmnopqrstuvwxyz '+t for t in ['orchard apple harvest','telescope stars planets',
              'river water stones','violin piano music','garden flower seeds']])
    parent = datasets.prepare(root, [{'name':f'{i}.txt','text':text} for i,text in enumerate(texts)], True, 'utf8_bytes')
    if special:
        config = {'special_tokens':{'pad':'<PAD>','bos':'<BOS>','eos':'<EOS>','unk':'<UNK>'},'unknown_policy':'replace'}
    else:config = {}
    record = experiments.train(root, parent['id'], True, parent, {'algorithm':algorithm,'vocabulary_cap':cap,**config})
    return parent,record


class AdoptionTests(unittest.TestCase):
    def test_new_immutable_version_preserves_permissions_and_splits_separate_training_approval(self):
        with TemporaryDirectory() as root:
            parent, exp = fixture(root)
            # Source permission records and derivation must survive selection unchanged.
            parent = decoder_licenses.declare(root,parent['id'],True,parent,parent['sources'][0]['source_sha256'],'user_created','Local QA author')
            exp = experiments.train(root,parent['id'],True,parent,exp['config'])
            before = {p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            child = adoptions.adopt(root, exp['id'], True, exp, parent)
            self.assertNotEqual(child['id'],parent['id'])
            for field in ['sources','splits','dataset_sha256','license_declarations','unique_documents']:
                self.assertEqual(child[field],parent[field])
            self.assertEqual(child['derivation']['parent_derivation'],parent['derivation'])
            self.assertFalse(child['tokenizer_selection']['model_training_approved'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse((Path(root)/'decoder-trials').exists())
            manifest,tok,rows,batches = training.preflight(root,child)
            self.assertIsInstance(tok,ModelTokenizer)
            self.assertTrue(all(tok.decode(tok.encode(row['text']))==row['text'] for row in rows))
            self.assertEqual(datasets.quality_report(root,child['id'])['token_distribution']['overall']['unknown_tokens'],0)
            self.assertEqual(trials.specification(child)['recipe_contract']['pipeline']['stages']['tokenization']['version'],2)
            with self.assertRaises(ValueError):trials.start(root,False,Mock(),dataset=child)
            importlib.reload(adoptions)
            self.assertEqual(datasets.read(root,child['id']),child)
            declared = decoder_licenses.declare(root,child['id'],True,child,child['sources'][0]['source_sha256'],'permission_recorded','Independent permission note')
            self.assertEqual(datasets.read(root,declared['id']),declared)

    def test_rejects_unapproved_stale_lossy_or_oversized_before_publishing(self):
        with TemporaryDirectory() as root:
            parent, exp = fixture(root,multilingual=True,algorithm='unigram')
            before = sorted(str(p) for p in Path(root).rglob('*'))
            for confirmed, reviewed, dataset in [(False,exp,parent),(True,{},parent),(True,exp,{})]:
                with self.assertRaises(ValueError):adoptions.adopt(root,exp['id'],confirmed,reviewed,dataset)
            with self.assertRaisesRegex(ValueError,'losslessly'):adoptions.adopt(root,exp['id'],True,exp,parent)
            self.assertEqual(before,sorted(str(p) for p in Path(root).rglob('*')))
            parent,exp = fixture(root,algorithm='byte_level_bpe',cap=320,special=False)
            with self.assertRaisesRegex(ValueError,'256'):adoptions.adopt(root,exp['id'],True,exp,parent)

    def test_failed_atomic_publication_cleans_staging_and_preserves_parent(self):
        with TemporaryDirectory() as root:
            parent,exp = fixture(root)
            before = {p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            with patch.object(Path,'rename',side_effect=OSError('fixture publication failure')):
                with self.assertRaises(OSError):adoptions.adopt(root,exp['id'],True,exp,parent)
            self.assertEqual(before,{p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()})
            self.assertFalse(any(p.name.startswith('.tokenizer-selection-') for p in (Path(root)/'decoder-datasets').iterdir()))

    def test_stale_selection_during_publication_and_tampered_child_are_rejected(self):
        with TemporaryDirectory() as root:
            parent,exp = fixture(root)
            before = {p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            with patch.object(experiments,'read',side_effect=[exp,exp,exp,{**exp,'revision':'0'*64}]):
                with self.assertRaisesRegex(ValueError,'changed during'):
                    adoptions.adopt(root,exp['id'],True,exp,parent)
            self.assertEqual(before,{p:p.read_bytes() for p in Path(root).rglob('*') if p.is_file()})
            child=adoptions.adopt(root,exp['id'],True,exp,parent)
            folder=Path(root)/'decoder-datasets'/child['id']
            changed=json.loads(json.dumps(child));changed['tokenizer_selection']['model_training_approved']=True
            (folder/'manifest.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'approval'):datasets.read(root,child['id'])
            (folder/'manifest.json').write_text(json.dumps(child))
            artifact=json.loads((folder/'tokenizer.json').read_text())
            artifact['codec']['base']['training_documents_sha256']='0'*64
            tok=Tokenizer.restore(artifact)
            (folder/'tokenizer.json').write_text(json.dumps(artifact))
            child['files']['tokenizer.json']=file_digest(folder/'tokenizer.json')
            child['tokenizer']['sha256']=tok.fingerprint()
            (folder/'manifest.json').write_text(json.dumps(child))
            with self.assertRaisesRegex(ValueError,'training-only fit'):datasets.read(root,child['id'])

    def test_all_codecs_checkpoint_bundle_versions_and_policy_tampering(self):
        for algorithm,cap in [('character_bpe',128),('unigram',128),('byte_level_bpe',256)]:
            with self.subTest(algorithm=algorithm), TemporaryDirectory() as root:
                parent,exp = fixture(root,algorithm,cap,special=algorithm!='byte_level_bpe')
                child=adoptions.adopt(root,exp['id'],True,exp,parent)
                _,tok,rows,_=training.preflight(root,child)
                restored=Tokenizer.restore(tok.artifact())
                self.assertEqual(tok.fingerprint(),restored.fingerprint())
                if algorithm != 'byte_level_bpe':
                    with self.assertRaises(ValueError):tok.encode('unseen Ω')
                else:self.assertEqual(tok.decode(tok.encode('unseen Ω')),'unseen Ω')
                model=Decoder({'vocab_size':len(tok.vocabulary)})
                record={'origin':'fresh','steps':0}
                manifest=bundles.save(Path(root)/'bundle',model,tok,record,'pretraining_local')
                loaded_model,loaded_tok,loaded_manifest=bundles.load(Path(root)/'bundle')
                self.assertEqual(loaded_manifest['stages']['tokenization'],2)
                self.assertEqual(loaded_tok.artifact(),tok.artifact())
                expected=checkpoints.revision(model.config,tok,[row['text'] for row in rows if row['split']=='train'])
                checkpoints.save(Path(root)/'checkpoint',model,tok,expected,50,'pretraining_local')
                self.assertEqual(checkpoints.load(Path(root)/'checkpoint',expected)[1].artifact(),tok.artifact())
                artifact=tok.artifact();artifact['input_policy']='replace'
                with self.assertRaises(ValueError):Tokenizer.restore(artifact)
                path=Path(root)/'bundle'/'manifest.json';manifest['stages']['tokenization']=1;path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'version'):bundles.load(path.parent)

    def test_generated_invalid_byte_preview_is_explicit_but_input_stays_lossless(self):
        selection={'parent_dataset_id':'a'*32,'experiment_id':'b'*32,'parent_manifest_sha256':'c'*64,'experiment_revision':'d'*64,'approval_sha256':'e'*64}
        tok=ModelTokenizer(ByteBPE.fit(['hello world'],256).artifact(),selection)
        self.assertEqual(tok.decode([255]),'�')
        self.assertEqual(tok.decode(tok.encode('café')),'café')
        with self.assertRaises(ValueError):tok.decode([256])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Opt-in actual local Metal execution')
    def test_actual_metal_trial_saves_fitted_tokenizer_with_model_and_checkpoint(self):
        from backend import recipe_contracts
        with TemporaryDirectory() as root:
            parent,exp=fixture(root,algorithm='unigram')
            child=adoptions.adopt(root,exp['id'],True,exp,parent)
            result=training.run(recipe_contracts.initialize_recipe,root,child,Path(root)/'artifacts')
            self.assertEqual(result['checkpoint']['completed_steps'],50)
            model,tok,manifest=bundles.load(Path(root)/'artifacts'/'bundle')
            self.assertIsInstance(tok,ModelTokenizer)
            self.assertEqual(manifest['training']['steps'],100)
            self.assertEqual(manifest['training']['review_sha256'],digest(child))
            self.assertEqual(manifest['config']['vocab_size'],exp['vocabulary_size'])
            self.assertEqual(manifest['tokenizer_sha256'],child['tokenizer']['sha256'])
