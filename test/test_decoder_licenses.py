import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend import decoder_datasets as datasets, decoder_licenses as licenses


class LicenseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.parent=datasets.prepare(self.root,[
            {'name':'a.txt','text':'First locally created document with café text.'},
            {'name':'copy.txt','text':'First locally created document with café text.'},
            {'name':'b.txt','text':'Second distinct fixture with a different original source.'},
            {'name':'c.txt','text':'Third source keeps independent local content.'}],True,'utf8_bytes')
        self.source=self.parent['sources'][0]['source_sha256']

    def declare(self,parent=None,source=None):
        parent=parent or self.parent
        return licenses.declare(self.root,parent['id'],True,parent,source or self.source,
                                'user_created','Created locally for this fixture.')

    def test_new_version_preserves_bytes_and_records_exact_source_declaration(self):
        folder=self.root/'decoder-datasets'/self.parent['id']
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        child=self.declare()
        self.assertNotEqual(child['id'],self.parent['id'])
        self.assertEqual(child['dataset_sha256'],self.parent['dataset_sha256'])
        self.assertEqual(child['files'],self.parent['files'])
        self.assertEqual(child['status'],'prepared_for_review')
        self.assertEqual(datasets.read(self.root,child['id']),child)
        for source in child['sources']:
            expected='user_declared_creation' if source['source_sha256']==self.source else 'user_provided_not_reviewed'
            self.assertEqual(source['license'],expected)
        self.assertEqual(child['derivation']['parent_manifest_sha256'],datasets.digest(self.parent))
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        for name in child['files']:
            self.assertEqual((self.root/'decoder-datasets'/child['id']/name).read_bytes(),before[name])
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_permission_notes_survive_export_and_additional_source_reviews(self):
        first=self.declare()
        second_source=next(s['source_sha256'] for s in first['sources'] if s['source_sha256']!=self.source)
        child=licenses.declare(self.root,first['id'],True,first,second_source,'permission_recorded','Local evidence reference: fixture grant 7.')
        self.assertEqual(len(child['license_declarations']),2)
        review=datasets.export_review(self.root,child['id'])
        export=datasets.export_dataset(self.root,child['id'],True,review['revision'])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(export['data']))) as archive:
            saved=json.loads(archive.read('manifest.json'))
            self.assertEqual(saved,child)
            self.assertTrue(saved['license_declarations'][self.source]['user_declared'])
            self.assertEqual(saved['license_declarations'][second_source]['note'],'Local evidence reference: fixture grant 7.')
        self.assertEqual(child['derivation']['previous_derivation'],first['derivation'])

    def test_consent_stale_review_invalid_source_and_notes_leave_originals_only(self):
        before=set((self.root/'decoder-datasets').iterdir())
        for consent,parent,source,basis,note in (
            (False,self.parent,self.source,'user_created','note'),
            (1,self.parent,self.source,'user_created','note'),
            (True,dict(self.parent,status='changed'),self.source,'user_created','note'),
            (True,self.parent,'f'*64,'user_created','note'),
            (True,self.parent,self.source,'verified_by_almg','note'),
            (True,self.parent,self.source,'user_created',' '),
            (True,self.parent,self.source,'user_created','x'*1001)):
            with self.assertRaises(ValueError):
                licenses.declare(self.root,self.parent['id'],consent,parent,source,basis,note)
        self.assertEqual(before,set((self.root/'decoder-datasets').iterdir()))
        self.assertFalse(list((self.root/'decoder-datasets').glob('.permission-*')))

    def test_unsupported_declaration_metadata_rejected_and_legacy_unchanged(self):
        child=self.declare();path=self.root/'decoder-datasets'/child['id']/'manifest.json'
        changed=json.loads(path.read_text());changed['license_declarations'][self.source]['user_declared']=False
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'permission declarations'):datasets.read(self.root,child['id'])
        self.assertEqual(datasets.read(self.root,self.parent['id']),self.parent)
        child=self.declare()
        with self.assertRaisesRegex(ValueError,'already recorded'):
            licenses.declare(self.root,child['id'],True,child,self.source,'user_created','Created locally for this fixture.')


if __name__=='__main__':unittest.main()
