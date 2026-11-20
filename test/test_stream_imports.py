import base64
import importlib
import io
import hashlib
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from backend import decoder_stream_imports as imports,decoder_stream_archives as archives,decoder_stream_training as training
from backend.run_manifest import digest
from test_stream_archives import passing_fixture


class StreamImportTests(unittest.TestCase):
    def archive(self,root):
        run,_,_=passing_fixture(root)
        return archives.export(root,run['id'],True,run['revision'],archives.review(root,run['id'],True,run['revision']))['data']

    def test_consent_limits_and_unknown_zip_members_reject(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):imports.import_private(root,False,'private.zip','')
            for data in ('invalid base64!',base64.b64encode(b'not a ZIP').decode(),'a'*(12*1024*1024+1)):
                with self.assertRaises(ValueError):imports.import_private(root,True,'private.zip',data)
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:archive.writestr('../outside','bad')
            with self.assertRaises(ValueError):imports.import_private(root,True,'private.zip',base64.b64encode(output.getvalue()).decode())
            self.assertEqual(imports.list_imports(root,True),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires genuine passing trained archive')
    def test_isolated_restart_exact_prompt_preview_and_model_integrity(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);encoded=self.archive(root);receiver=root/'receiver';receiver.mkdir()
            record=imports.import_private(receiver,True,'private.zip',encoded)
            self.assertFalse(record['training_approved']);self.assertFalse(record['release_approved'])
            self.assertEqual(record['evaluation_status'],'archived_claims_not_re_evaluated_source_excluded')
            before={p:p.read_bytes() for p in imports._folder(receiver,record['id']).rglob('*') if p.is_file() and p.name!='import.json'}
            importlib.reload(imports);self.assertEqual(imports.read(receiver,record['id']),record)
            with patch.object(training,'read',side_effect=AssertionError('Source training run must not be accessed')):
                first=imports.preview(receiver,record['id'],True,' aaaa ',12)
            self.assertEqual(first['prompt'],' aaaa ');self.assertEqual(len(first['generated_token_ids']),12)
            importlib.reload(imports);second=imports.preview(receiver,record['id'],True,' aaaa ',12)
            self.assertEqual(first['generated_token_ids'],second['generated_token_ids']);self.assertEqual(first['text'],second['text'])
            self.assertEqual(len(imports.read(receiver,record['id'])['previews']),2)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            with self.assertRaises(ValueError):imports.preview(receiver,record['id'],False,'aaaa',12)
            with self.assertRaises(ValueError):imports.preview(receiver,record['id'],True,'a'*17,12)
            (imports._folder(receiver,record['id'])/'bundle/decoder.json').write_text('{}')
            with self.assertRaises(ValueError):imports.read(receiver,record['id'])
            self.assertEqual(imports.list_imports(receiver,True),[])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires genuine passing trained archive')
    def test_changed_payload_receipt_symlink_extra_size_and_failed_publication_leave_no_import(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);encoded=self.archive(root);data=base64.b64decode(encoded)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:contents={name:archive.read(name) for name in archive.namelist()}
            for mode in ('payload','receipt','symlink','extra','oversized'):
                modified=dict(contents)
                if mode=='receipt':
                    receipt=json.loads(modified['preview.json']);receipt['generated_token_ids'][0]=(receipt['generated_token_ids'][0]+1)%256
                    receipt['revision']=digest({k:v for k,v in receipt.items() if k!='revision'});modified['preview.json']=json.dumps(receipt).encode()
                    envelope=json.loads(modified['export-manifest.json']);review=envelope['approved_review']
                    review['preview_revision']=receipt['revision'];review['files']['preview.json']=hashlib.sha256(modified['preview.json']).hexdigest()
                    review['revision']=digest({k:v for k,v in review.items() if k!='revision'});modified['export-manifest.json']=json.dumps(envelope).encode()
                output=io.BytesIO()
                with zipfile.ZipFile(output,'w') as archive:
                    for name,value in modified.items():
                        if mode=='payload' and name=='preview.json':value=b'{}'
                        if mode=='oversized' and name=='bundle/tokenizer.json':value=b'x'*(128*1024+1)
                        if mode=='symlink' and name=='bundle/decoder.json':
                            info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,value)
                        else:archive.writestr(name,value)
                    if mode=='extra':archive.writestr('extra.json','{}')
                with self.assertRaises(ValueError):imports.import_private(root,True,'bad.zip',base64.b64encode(output.getvalue()).decode())
            with patch.object(Path,'rename',side_effect=OSError('publication failed')):
                with self.assertRaises(ValueError):imports.import_private(root,True,'private.zip',encoded)
            self.assertEqual(imports.list_imports(root,True),[])
