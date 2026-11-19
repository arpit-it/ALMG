import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_exports as exports


class StreamIndexExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        raw=('\n'.join(f'Local original line {i} with café and private@example.test' for i in range(300))+'\n').encode()
        source=streams.create(self.root,'source.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)

    def test_bounded_export_reconstructs_exact_index_and_provenance_without_source_or_audits(self):
        index_id=self.index['id'];folder=self.root/'decoder-stream-indexes'/index_id
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        review=exports.review(self.root,index_id)
        self.assertFalse(review['includes_original_raw_source']);self.assertFalse(review['includes_saved_audits'])
        self.assertFalse(review['includes_training_approvals'])
        restored=self.root/'restored/decoder-stream-indexes'/index_id;restored.mkdir(parents=True)
        for name,metadata in review['files'].items():
            data=bytearray()
            while len(data)<metadata['bytes']:
                block=exports.chunk(self.root,index_id,True,review,name,len(data),4096)
                decoded=base64.b64decode(block['data']);self.assertLessEqual(len(decoded),4096);data.extend(decoded)
            self.assertEqual(bytes(data),before[name]);self.assertEqual(hashlib.sha256(data).hexdigest(),metadata['sha256'])
            (restored/name).write_bytes(data)
        self.assertEqual(exports.seal(self.root,index_id,True,review)['export_manifest'],review)
        self.assertEqual(indexes.read(self.root/'restored',index_id),self.index)
        self.assertEqual(review['source_provenance']['source_sha256'],self.index['source_sha256'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_unapproved_stale_changed_or_arbitrary_file_requests_reject(self):
        index_id=self.index['id'];review=exports.review(self.root,index_id)
        for confirmed,name,offset,limit in ((False,'records.sqlite3',0,4096),(True,'../source.bin',0,4096),
                                          (True,'records.sqlite3',False,4096),(True,'records.sqlite3',0,65537)):
            with self.assertRaises(ValueError):exports.chunk(self.root,index_id,confirmed,review,name,offset,limit)
        changed=dict(review,revision='stale')
        with self.assertRaisesRegex(ValueError,'review changed'):exports.chunk(self.root,index_id,True,changed,'records.sqlite3',0)
        with self.assertRaises(ValueError):exports.chunk(self.root,index_id,True,review,'records.sqlite3',review['files']['records.sqlite3']['bytes'])
        database=self.root/'decoder-stream-indexes'/index_id/'records.sqlite3'
        with database.open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'review changed'):exports.chunk(self.root,index_id,True,review,'records.sqlite3',0)
        with self.assertRaises(ValueError):exports.seal(self.root,index_id,True,review)

    def test_incomplete_index_and_false_seal_consent_cannot_export(self):
        pending=indexes.begin(self.root,self.index['source_id'],True)
        with self.assertRaisesRegex(ValueError,'Complete and verify'):exports.review(self.root,pending['id'])
        review=exports.review(self.root,self.index['id'])
        with self.assertRaises(ValueError):exports.seal(self.root,self.index['id'],False,review)


if __name__=='__main__':unittest.main()
