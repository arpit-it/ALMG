import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_permissions as permissions, decoder_stream_exports as exports


class StreamPermissionTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        raw=b'Local orchard harvest document\nDistant galaxy telescope document\nCoastal ocean waves document\n'
        source=streams.create(self.root,'source.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)
        self.id=self.index['id']

    def test_immutable_history_is_exported_without_mutating_original_or_granting_approval(self):
        folder=indexes._folder(self.root,self.id);before={p.name:p.read_bytes() for p in folder.iterdir()}
        review=permissions.review(self.root,self.id);self.assertEqual(review['declarations'],[])
        original_export=exports.review(self.root,self.id)
        one=permissions.declare(self.root,self.id,True,review,'user_created',' Synthetic source created locally. ')
        first=(self.root/'decoder-stream-permissions'/self.id/'0001.json').read_bytes()
        two=permissions.declare(self.root,self.id,True,one,'needs_review','Further review pending.')
        self.assertEqual((self.root/'decoder-stream-permissions'/self.id/'0001.json').read_bytes(),first)
        self.assertEqual(two['declarations'][0],one['latest_declaration'])
        self.assertEqual(two['latest_declaration']['previous_revision'],one['latest_declaration']['revision'])
        self.assertFalse(two['permission_verified']);self.assertFalse(two['training_approved'])
        self.assertEqual(two['source_provenance']['source_sha256'],self.index['source_sha256'])
        with self.assertRaisesRegex(ValueError,'review changed'):exports.seal(self.root,self.id,True,original_export)
        exported=exports.review(self.root,self.id)
        self.assertEqual(exported['schema_version'],2)
        self.assertEqual(exported['source_permission_review'],two)
        self.assertEqual(exports.seal(self.root,self.id,True,exported)['export_manifest'],exported)
        self.assertEqual(permissions.review(self.root,self.id),two)
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_unapproved_stale_invalid_and_duplicate_declarations_reject(self):
        review=permissions.review(self.root,self.id)
        for confirmed,basis,note in [(False,'user_created','note'),(True,'unknown','note'),(True,'needs_review',''),(True,'user_created','x'*1001)]:
            with self.assertRaises(ValueError):permissions.declare(self.root,self.id,confirmed,review,basis,note)
        one=permissions.declare(self.root,self.id,True,review,'user_created','note')
        with self.assertRaisesRegex(ValueError,'review changed'):permissions.declare(self.root,self.id,True,review,'needs_review','new')
        with self.assertRaisesRegex(ValueError,'already recorded'):permissions.declare(self.root,self.id,True,one,'user_created','note')
        self.assertEqual(permissions.review(self.root,self.id),one)

    def test_tampered_history_rejects_export_and_incomplete_index_rejects_declaration(self):
        review=permissions.review(self.root,self.id)
        permissions.declare(self.root,self.id,True,review,'needs_review','note')
        path=self.root/'decoder-stream-permissions'/self.id/'0001.json'
        changed=json.loads(path.read_text());changed['note']='changed';path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'integrity'):permissions.review(self.root,self.id)
        with self.assertRaises(ValueError):exports.review(self.root,self.id)
        pending=indexes.begin(self.root,self.index['source_id'],True)
        with self.assertRaisesRegex(ValueError,'Complete text indexing'):permissions.review(self.root,pending['id'])


if __name__=='__main__':unittest.main()
