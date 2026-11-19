"""Strict private ZIP import is isolated from training and public release."""
import base64
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from backend import decoder_bundle, decoder_trials
from backend.decoder_recipe import Decoder
from backend.decoder_tokenizer import Tokenizer


class DecoderImportTest(unittest.TestCase):
    def archive(self, root):
        source=root/'source'
        manifest=decoder_bundle.save(source,Decoder({'vocab_size':4}),Tokenizer.fit(['amber birch cedar dune']),{'fixture':True})
        contents={'bundle/'+p.name:p.read_bytes() for p in source.iterdir()}
        evaluation={'passed':True,'claimed_score':1.0}
        preview={'prompt':'claimed'}
        review={'schema_version':1,'format':'almg-private-decoder-export-v1','bundle_manifest_sha256':decoder_bundle.digest(manifest),
                'files':{name:hashlib.sha256(data).hexdigest() for name,data in contents.items()},
                'evaluation_revision':decoder_bundle.digest(evaluation),'preview_revision':decoder_bundle.digest(preview)}
        review['revision']=decoder_bundle.digest(review)
        contents['export-manifest.json']=json.dumps({'schema_version':1,'format':review['format'],
            'approved_review':review,'evaluation':evaluation,'preview':preview}).encode()
        return contents

    def encode(self, contents, extra=None):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,data in contents.items():archive.writestr(name,data)
            if extra is not None:archive.writestr(*extra)
        return base64.b64encode(output.getvalue()).decode()

    def test_import_verifies_private_files_and_preview_without_trusting_claimed_quality(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);contents=self.archive(root);encoded=self.encode(contents)
            record=decoder_trials.import_private(root,True,'fixture.zip',encoded)
            self.assertEqual(record['scope'],'private_cpu_preview_only')
            self.assertEqual(record['evaluation_status'],'not_re_evaluated_dataset_excluded')
            self.assertEqual(decoder_trials.read_import(root,record['id']),record)
            result=decoder_trials.preview_import(root,record['id'],True,'amber')
            self.assertEqual(result['import_id'],record['id']);self.assertNotIn('trial_id',result)
            self.assertEqual(len(result['generated_token_ids']),12)
            saved=decoder_trials.read_import(root,record['id']);self.assertEqual(saved['previews'],[result])
            again=decoder_trials.import_private(root,True,'same.zip',encoded)
            self.assertNotEqual(again['id'],record['id'])
            self.assertEqual(len(decoder_trials.list_imports(root)),2)
            self.assertFalse((root/'decoder-trials').exists())
            with self.assertRaises(ValueError):decoder_trials.start(root,True,lambda *args:None,trial_id=record['id'])
            with self.assertRaises(ValueError):decoder_trials.export_review(root,record['id'])

    def test_missing_consent_hash_changes_and_unsafe_members_never_publish_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);contents=self.archive(root)
            with self.assertRaises(ValueError):decoder_trials.import_private(root,False,'f.zip',self.encode(contents))
            changed={**contents,'bundle/decoder.json':b'{}'}
            with self.assertRaises(ValueError):decoder_trials.import_private(root,True,'f.zip',self.encode(changed))
            for name in ('../outside','extra.json'):
                with self.assertRaises(ValueError):decoder_trials.import_private(root,True,'f.zip',self.encode(contents,(name,b'bad')))
            symlink=zipfile.ZipInfo('bundle/decoder.json');symlink.create_system=3;symlink.external_attr=(stat.S_IFLNK|0o777)<<16
            original={k:v for k,v in contents.items() if k!='bundle/decoder.json'}
            with self.assertRaises(ValueError):decoder_trials.import_private(root,True,'f.zip',self.encode(original,(symlink,b'/tmp/target')))
            oversized={**contents,'export-manifest.json':b'x'*(512*1024+1)}
            with self.assertRaises(ValueError):decoder_trials.import_private(root,True,'f.zip',self.encode(oversized))
            self.assertEqual(decoder_trials.list_imports(root),[])
            self.assertFalse((root/'outside').exists())

    def test_preview_checks_consent_and_rejects_later_bundle_or_provenance_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record=decoder_trials.import_private(root,True,'f.zip',self.encode(self.archive(root)))
            with self.assertRaises(ValueError):decoder_trials.preview_import(root,record['id'],False,'amber')
            folder=decoder_trials.import_folder(root,record['id'])
            (folder/'import.json').write_text(json.dumps({**record,'evaluation_status':'verified'}))
            with self.assertRaises(ValueError):decoder_trials.read_import(root,record['id'])
            (folder/'import.json').write_text(json.dumps(record))
            (folder/'export-manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'integrity changed'):decoder_trials.read_import(root,record['id'])
            (folder/'bundle/decoder.json').write_text('{}')
            with self.assertRaises(ValueError):decoder_trials.preview_import(root,record['id'],True,'amber')
