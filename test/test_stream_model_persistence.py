from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_bundle as bundles,decoder_stream_learned_windows as windows,decoder_stream_persistence as persistence,decoder_checkpoint as checkpoints
from backend.decoder_tokenizer import Tokenizer
from backend.decoder_recipe import Decoder
from backend.decoder_stream_model_tokenizer import StreamModelTokenizer
from test_stream_unigram_model_inputs import pipeline,finish


class StreamPersistenceTests(unittest.TestCase):
    def test_maximum_stream_vocabulary_bundle_and_pipeline_downgrade_rejection(self):
        from backend.decoder_stream_iterative_bpe import StreamByteBPE
        codec=StreamByteBPE([[value,value] for value in range(256)],'a'*64,512,3)
        approval={'version':1,'scope':'fresh_stream_model_persistence_only','windows_id':'b'*32,'windows_revision':'c'*64,
                  'tokenizer_sha256':bundles.digest(codec.artifact()),'inspected_batch_sha256':'d'*64,'seed':7}
        selection={'windows_id':'b'*32,'windows_revision':'c'*64,'fit_id':'e'*32,'fit_revision':'f'*64,'index_id':'a'*32,
                   'index_revision':'a'*64,'source_sha256':'b'*64,'tokenizer_sha256':approval['tokenizer_sha256'],'approval_sha256':bundles.digest(approval)}
        tokenizer=StreamModelTokenizer(codec.artifact(),selection)
        record={'kind':'stream_model_persistence_check','schema_version':1,'approval':approval,'approval_sha256':bundles.digest(approval),
                'optimizer_updates':0,'pretrained_weights_loaded':False,'model_training_approved':False,'release_approved':False}
        with TemporaryDirectory() as temporary:
            folder=Path(temporary)/'bundle';model=Decoder({'vocab_size':512,'seed':7})
            bundles.save(folder,model,tokenizer,record,pretraining_stage='initialization_check')
            loaded,restored,manifest=bundles.load(folder)
            self.assertEqual(manifest['stages']['architecture'],2);self.assertEqual(len(restored.vocabulary),512)
            np.testing.assert_array_equal(model.logits([[0,511]]),loaded.logits([[0,511]]))
            path=folder/'manifest.json';manifest['stages']['tokenization']=2;path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):bundles.load(folder)

    def setup_stream(self,root):
        fitted,comparison,evidence=pipeline(root)
        record=finish(windows,root,windows.begin(root,comparison['id'],evidence['id'],True,windows.review(root,comparison['id'],evidence['id'])))
        return record,windows.read_batch(root,record['id'],True,record)

    def test_source_bound_bundle_checkpoint_policy_and_exact_outputs_without_training(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,batch=self.setup_stream(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report=persistence.run(root,record['id'],True,record,batch)
            self.assertEqual(report['optimizer_updates'],0);self.assertEqual(report['tokenization_version'],3);self.assertEqual(report['cpu_logit_max_error'],0)
            self.assertTrue(report['all_parameter_tensors_equal']);self.assertFalse(report['model_training_approved'])
            folder=persistence._folder(root,record['id'])/report['id']/'bundle'
            model,tokenizer,manifest=bundles.load(folder)
            self.assertEqual(manifest['stages'],{'architecture':1,'tokenization':3,'initialization_check':1,'artifact':1})
            self.assertEqual(tokenizer.artifact(),Tokenizer.restore(tokenizer.artifact()).artifact())
            self.assertEqual(manifest['pipeline']['stages']['pretraining']['status'],'initialization_only_no_optimizer_updates')
            self.assertEqual(manifest['pipeline']['stages']['dataset_preparation']['version'],2)
            self.assertEqual(manifest['pipeline']['stages']['evaluation']['interface'],'cpu_model_tokenizer_roundtrip')
            with self.assertRaisesRegex(ValueError,'separately approved'):tokenizer.validate_training_documents(['banana'])
            with self.assertRaises(ValueError):bundles.save(root/'unapproved-training',model,tokenizer,manifest['training'],pretraining_stage='pretraining_local')
            revision=checkpoints.revision(model.config,tokenizer,[])
            with self.assertRaises(ValueError):checkpoints.save(root/'unapproved-checkpoint',model,tokenizer,revision,50,pretraining_stage='pretraining_local')
            model.parameters['head'][0,0]+=.1
            with self.assertRaisesRegex(ValueError,'modified parameters'):bundles.save(root/'modified',model,tokenizer,manifest['training'],pretraining_stage='initialization_check')
            self.assertFalse((root/'modified').exists())
            self.assertEqual(persistence.list_reports(root,record['id'],True),[report]);self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            altered=deepcopy(tokenizer.artifact());altered['training_approved']=True
            with self.assertRaises(ValueError):Tokenizer.restore(altered)
            policy=deepcopy(manifest['training']);policy['optimizer_updates']=1
            with self.assertRaises(ValueError):tokenizer.validate_persistence_record(policy)

    def test_consent_stale_batch_and_post_save_source_checks(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);record,batch=self.setup_stream(root)
            with patch.object(persistence.recipe_contracts,'initialize_recipe') as initialize:
                with self.assertRaises(ValueError):persistence.run(root,record['id'],False,record,batch)
                with self.assertRaisesRegex(ValueError,'inspected'):persistence.run(root,record['id'],True,record,{})
                initialize.assert_not_called()
            self.assertFalse((root/'decoder-stream-persistence-checks').exists())
            read=persistence.batches.read_batch;calls=0
            def changed(*args,**kwargs):
                nonlocal calls
                calls+=1;result=read(*args,**kwargs)
                return {**result,'changed':True} if calls==2 else result
            with patch.object(persistence.batches,'read_batch',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during persistence'):persistence.run(root,record['id'],True,record,batch)
            self.assertEqual(persistence.list_reports(root,record['id'],True),[])

    def test_all_stream_codec_families_and_preview_limits(self):
        from backend import decoder_stream_iterative_bpe as byte,decoder_stream_character_bpe as char,decoder_stream_unigram as uni
        from backend.decoder_bpe import ByteBPE
        from backend.decoder_character_bpe import CharacterBPE
        from backend.decoder_unigram import UnigramTokenizer
        for family in ('byte','character','unigram'):
            if family=='byte':
                small=ByteBPE.fit(['banana café 世界 banana'],260);codec=byte.StreamByteBPE(small.merges,'a'*64,260,3)
            elif family=='character':
                small=CharacterBPE.fit(['banana café 世界 banana'],64);codec=char.StreamCharacterBPE(small.alphabet,small.merges,'a'*64,64,3)
            else:
                small=UnigramTokenizer.fit(['banana café 世界 banana'],64);codec=uni.StreamUnigram(small.alphabet,small.pieces,small.probabilities,'a'*64,64,3,'b'*64,small.history)
            artifact=codec.artifact();selection={key:'a'*size for key,size in {'windows_id':32,'windows_revision':64,'fit_id':32,'fit_revision':64,'index_id':32,'index_revision':64,'source_sha256':64,'approval_sha256':64}.items()};selection['tokenizer_sha256']=bundles.digest(artifact)
            wrapper=StreamModelTokenizer(artifact,selection);restored=Tokenizer.restore(wrapper.artifact())
            text='banana café 世界';self.assertEqual(restored.decode(restored.encode(text)),text)
            self.assertEqual(restored.decode_preview(restored.encode('banana')), 'banana')
            with self.assertRaises(ValueError):restored.decode_preview([0]*161)
            with self.assertRaises(ValueError):restored.decode_preview([len(wrapper.vocabulary)])
            if family=='byte':self.assertEqual(restored.decode_preview([255]),'�')
