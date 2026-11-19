"""Private ZIP export requires freshly reproduced evaluation and preview receipts."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from backend import decoder_trials, decoder_bundle, decoder_datasets, decoder_dataset_training
from backend.decoder_recipe import Decoder


class DecoderExportTest(unittest.TestCase):
    def fixture(self, root):
        words = ['amber','birch','cedar','dune']
        docs = [{'name':str(i),'text':' '.join(words[(i+j)%4] for j in range(8+i))} for i in range(6)]
        dataset = decoder_datasets.prepare(root, docs, True)
        _,tokenizer,_,_ = decoder_dataset_training.preflight(root,dataset)
        record = {'schema_version':1,'id':'a'*32,'created_at':'fixture','status':'complete','dataset':dataset,'approval':{'id':'retained'}}
        decoder_trials.write(root,record)
        path=decoder_trials.folder(root,record['id'])/'artifacts/bundle'
        path.parent.mkdir(parents=True)
        model=Decoder({'vocab_size':4})
        for value in model.parameters.values(): value[:]=0
        model.parameters['token_embedding'][:,:4]=np.eye(4)
        for i in range(4): model.parameters['head'][i,(i+1)%4]=10
        training={'scope':'reviewed_local_text_trial','dataset_id':dataset['id'],'dataset_sha256':dataset['dataset_sha256'],
                  'review_sha256':decoder_bundle.digest(dataset),'evaluation':{'initial_train_loss':3.0}}
        decoder_bundle.save(path,model,tokenizer,training,pretraining_stage='pretraining_local')
        return record,path

    def ready(self,root,record):
        self.assertTrue(decoder_trials.evaluate(root,record['id'],True)['passed'])
        decoder_trials.preview(root,record['id'],True,'amber')

    def test_export_is_explicit_exact_private_self_contained_and_preserves_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record,path=self.fixture(root);self.ready(root,record)
            before={p.name:p.read_bytes() for p in path.iterdir()}
            review=decoder_trials.export_review(root,record['id'])
            self.assertFalse((root/'decoder-exports').exists())
            for confirmed,revision in ((False,review['revision']),(True,'stale')):
                with self.assertRaises(ValueError):decoder_trials.export_private(root,record['id'],confirmed,revision)
            self.assertFalse((root/'decoder-exports').exists())
            result=decoder_trials.export_private(root,record['id'],True,review['revision'])
            data=base64.b64decode(result['data']);self.assertEqual(hashlib.sha256(data).hexdigest(),result['archive_sha256'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),{'bundle/decoder.json','bundle/tokenizer.json','bundle/manifest.json','export-manifest.json'})
                manifest=json.loads(archive.read('export-manifest.json'))
                self.assertEqual(manifest['approved_review'],review)
                self.assertTrue(manifest['evaluation']['passed'])
                self.assertEqual(manifest['preview']['prompt'],'amber')
                archive.extractall(root/'unpacked')
            decoder_bundle.load(root/'unpacked/bundle')
            self.assertEqual((root/'decoder-exports'/result['id']/'bundle.zip').read_bytes(),data)
            saved=decoder_trials.read(root,record['id']);self.assertEqual(saved['status'],'complete')
            self.assertEqual(saved['approval'],record['approval'])
            self.assertEqual(len(saved['evaluations']),1);self.assertEqual(len(saved['previews']),1)
            self.assertEqual({p.name:p.read_bytes() for p in path.iterdir()},before)

    def test_missing_stale_or_forged_receipts_cannot_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record,_=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'evaluation and a private preview'):decoder_trials.export_review(root,record['id'])
            self.ready(root,record);review=decoder_trials.export_review(root,record['id'])
            decoder_trials.preview(root,record['id'],True,'birch')
            with self.assertRaisesRegex(ValueError,'review changed'):decoder_trials.export_private(root,record['id'],True,review['revision'])
            saved=decoder_trials.read(root,record['id']);saved['previews'][-1]['completion']='forged'
            decoder_trials.write(root,saved)
            with self.assertRaisesRegex(ValueError,'does not reproduce'):decoder_trials.export_review(root,record['id'])
            decoder_trials.preview(root,record['id'],True,'amber')
            saved=decoder_trials.read(root,record['id']);saved['evaluations'][-1]['metrics']['test']['next_token_accuracy']=.9
            decoder_trials.write(root,saved)
            with self.assertRaisesRegex(ValueError,'no longer matches'):decoder_trials.export_review(root,record['id'])
            self.assertFalse((root/'decoder-exports').exists())

    def test_bundle_tampering_invalidates_review_without_writing_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record,path=self.fixture(root);self.ready(root,record)
            review=decoder_trials.export_review(root,record['id'])
            (path/'decoder.json').write_text('{}')
            with self.assertRaises(ValueError):decoder_trials.export_private(root,record['id'],True,review['revision'])
            self.assertFalse((root/'decoder-exports').exists())
